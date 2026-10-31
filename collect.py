"""Collect deterministic observation/action pairs from rule-based teachers."""
import argparse
from pathlib import Path
from datetime import date, timedelta
import os
import numpy as np
import torch
from model import FEATURES, ROLE_HOME, ROLE_SOCIETY, ROLE_GRID, HivePolicy
from profiles import generate_profiles
from scheduling import schedule_home
from world import World
from world import PVGISWeatherProvider
from shield import project

def sample(seed: int, count: int, policy_model: HivePolicy | None = None, weather_date: date | None = None,
           weather_year: int = 2023, return_dates: bool = False):
    """Generate 48-step home sequences and role-labelled teacher actions."""
    rng = np.random.default_rng(seed); profiles = generate_profiles(60, seed); world = World(seed, demo_date=weather_date.isoformat() if weather_date else None, weather_year=weather_year); world.heat_start=72; world.heat_end=88
    if weather_date and not world.weather_is_real: world.day_of_year=weather_date.timetuple().tm_yday
    weather=[world.weather(step) for step in range(96)]
    solar_table={home.solar_kwp:[world.solar_kw(home.solar_kwp,step,weather[step][1]) for step in range(96)] for home in profiles}
    obs = np.zeros((count, 48, FEATURES), dtype=np.float32); acts = np.zeros((count, 7), dtype=np.float32); roles = np.zeros(count, dtype=np.int64)
    for i in range(count):
        world.heatwave=i%5==0
        home = profiles[int(rng.integers(len(profiles)))]; start = int(rng.integers(0, 96)); temp_bias = float(rng.uniform(-2, 5))
        role = i % 3; roles[i] = role
        if role == ROLE_HOME:
            room=world.weather(start)[0]+temp_bias; soc=home.battery_kwh*.5; ev_left=home.initial_ev_charge_need_kwh
            for j in range(48):
                s=(start+j)%96; temp,cloud,heat=weather[s]
                if world.heatwave and not world.weather_is_real and 72<=s<88: temp+=3; heat=temp>=43
                solar=solar_table[home.solar_kwp][s]; price=world.price(s); stress=bool(world.heatwave and 72<=s<88)
                feature=[s/96,(temp+temp_bias)/50,cloud,solar/8,world.price_feature(s),float(stress),home.solar_kwp/8,home.ac_count/4,home.ac_kw/2,home.ev_kw/8,home.battery_kwh/10,home.base_load_kw/2,home.comfort_weight/1.5,home.cost_weight/1.5,home.flexibility_weight,home.ev_energy_need_kwh/20,(room-home.temperature_setpoint_c)/10,(soc/home.battery_kwh if home.battery_kwh else 0)]
                obs[i,j]=feature
                group=int(home.id[1:])%3; hour=s/4
                pre_cool=bool(world.heatwave and world.heat_start-12<=s<world.heat_start and 15+group<=hour<16+group and solar>home.base_load_kw+home.ac_count*home.ac_kw)
                sched=schedule_home(home,s,temp+temp_bias,solar,price,stress,ev_left,room,soc,pre_cool,world)
                chosen=sched
                if policy_model is not None:
                    with torch.inference_mode(): raw=policy_model(torch.tensor([[feature]*48]),torch.tensor([ROLE_HOME])).squeeze(0).tolist()
                    candidate={'base_kw':home.base_load_kw,'ac_kw':raw[0]*6,'ev_kw':raw[1]*8,'geyser_kw':raw[2]*1.2,'other_kw':raw[3],'battery_charge_kw':raw[4]*3,'battery_discharge_kw':raw[5]*3,'solar_kw':solar,'comfort_deficit':raw[6]*10}
                    safe,_=project(candidate,home,step=s,battery_soc_kwh=soc,ev_remaining_kwh=ev_left,room_temp_c=room,outdoor_temp_c=temp+temp_bias)
                    from scheduling import Schedule
                    chosen=Schedule(**safe)
                acts[i]=[sched.ac_kw/6,sched.ev_kw/8,sched.geyser_kw/1.2,sched.other_kw/1,sched.battery_charge_kw/3,sched.battery_discharge_kw/3,sched.comfort_deficit/10]
                room=max(16,min(50,room+.015*(temp+temp_bias-room)-.7*chosen.ac_kw)); soc=min(home.battery_kwh,max(0,soc+chosen.battery_charge_kw*.25*home.battery_efficiency-chosen.battery_discharge_kw*.25/home.battery_efficiency)); ev_left=max(0,ev_left-chosen.ev_kw*.25)
        else:
            for j in range(48):
                s=(start+j)%96; temp,cloud,heat=weather[s]
                if world.heatwave and not world.weather_is_real and 72<=s<88: temp+=3; heat=temp>=43
                price=world.price(s); stress=float(heat or (world.heatwave and 72<=s<88))
                obs[i,j]=[s/96,temp/50,cloud,solar_table[home.solar_kwp][s]/8,world.price_feature(s),stress,home.solar_kwp/8,home.ac_count/4,home.ac_kw/2,home.ev_kw/8,home.battery_kwh/10,home.base_load_kw/2,home.comfort_weight/1.5,home.cost_weight/1.5,home.flexibility_weight,home.ev_energy_need_kwh/20,0,0]
                if role==ROLE_SOCIETY: acts[i]=[min(1.5,max(.5,1+stress*.25)),home.flexibility_weight,0,0,0,0,0]
                else: acts[i]=[world.price_feature(s),stress,.8 if stress else 1,0,0,0,0]
    if return_dates:
        label = (weather_date or (date.fromisoformat(world.demo_date) if world.demo_date else date(weather_year, 1, 1))).isoformat()
        return obs, roles, acts, np.asarray([label] * count, dtype="U10")
    return obs, roles, acts

def _date_partitions(year: int, demo_date: date, data_dir: Path):
    try:
        dates=[day for day in PVGISWeatherProvider(year,data_dir).dates]
    except (FileNotFoundError, ValueError):
        first=date(year,1,1); dates=[first+timedelta(days=i) for i in range(365+(1 if __import__('calendar').isleap(year) else 0))]
    if demo_date not in dates: raise ValueError(f'demo date {demo_date} is not available in cached year {year}')
    remaining=[day for day in dates if day!=demo_date]
    train_end=max(1,int(len(remaining)*.70)); valid_end=max(train_end+1,int(len(remaining)*.85))
    train_dates=remaining[:train_end]; validation_dates=remaining[train_end:valid_end]; test_dates=remaining[valid_end:]+[demo_date]
    assert demo_date not in train_dates and demo_date not in validation_dates and demo_date in test_dates
    return {'train':train_dates,'validation':validation_dates,'test':sorted(test_dates)}


def _sample_split(seed: int, count: int, dates: list[date], year: int, policy: HivePolicy | None):
    rng=np.random.default_rng(seed); buckets={day:0 for day in dates}
    chosen=rng.choice(len(dates),size=count,replace=True)
    for index in chosen: buckets[dates[int(index)]]+=1
    parts=[]
    for ordinal,(day,amount) in enumerate(buckets.items()):
        if amount:
            parts.append(sample(seed+ordinal*104729,amount,policy,day,year,return_dates=True))
    if not parts:
        return (np.empty((0,48,FEATURES),np.float32),np.empty((0,),np.int64),np.empty((0,7),np.float32),np.empty((0,),dtype='U10'))
    return tuple(np.concatenate([part[i] for part in parts]) for i in range(4))


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--samples',type=int,default=100000); parser.add_argument('--seed',type=int,default=11); parser.add_argument('--output',default='data/teacher.pt'); parser.add_argument('--dagger-model'); parser.add_argument('--dagger-rounds',type=int,choices=(0,1,2),default=0); parser.add_argument('--append',action='store_true'); parser.add_argument('--smoke',action='store_true'); parser.add_argument('--year',type=int,default=2023); parser.add_argument('--demo-date',help='Date reserved for test only; defaults to the hottest cached day at or above 43 C'); parser.add_argument('--data-dir',type=Path,default=Path('data/real')); args=parser.parse_args()
    if args.dagger_rounds and not args.dagger_model: parser.error('--dagger-model is required when --dagger-rounds is nonzero')
    count=512 if args.smoke else args.samples
    if count<3: parser.error('--samples must be at least 3 to populate train, validation, and test')
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    try: provider=PVGISWeatherProvider(args.year,args.data_dir)
    except (FileNotFoundError,ValueError): provider=None
    if args.demo_date:
        demo_date=date.fromisoformat(args.demo_date)
    elif provider:
        hot=[(day,temp) for day,temp in provider.daily_maxima() if temp>=43.0]
        demo_date=hot[0][0] if hot else provider.daily_maxima()[0][0]
    else:
        demo_date=date(args.year,7,1)
    try: split_dates=_date_partitions(args.year,demo_date,args.data_dir)
    except ValueError as exc: parser.error(str(exc))
    if args.dagger_rounds:
        checkpoint=torch.load(args.dagger_model,map_location='cpu',weights_only=True); policy=HivePolicy(); policy.load_state_dict(checkpoint['state_dict']); policy.eval()
    else: policy=None
    train_count=max(1,int(count*.70)); validation_count=max(1,int(count*.15)); test_count=count-train_count-validation_count
    if test_count<1: train_count-=1; test_count=1
    rng=np.random.default_rng(args.seed)
    partitions={}
    for name,n in (('train',train_count),('validation',validation_count),('test',test_count)):
        choices=split_dates[name]
        if name=='test':
            # Reserve at least one held-out sample specifically for the selected demo day.
            demo_n=max(1,int(n/len(choices)))
            chosen=[demo_date]*demo_n
            if n>demo_n: chosen.extend(choices[int(i)] for i in rng.integers(0,len(choices),size=n-demo_n))
        else: chosen=[choices[int(i)] for i in rng.integers(0,len(choices),size=n)]
        partitions[name]=_sample_split(args.seed+({'train':0,'validation':1,'test':2}[name]),n,choices,args.year,policy) if name!='test' else None
        if name=='test':
            # Keep the user-selected date in the test set, and use other held-out dates too.
            counts={day:chosen.count(day) for day in set(chosen)}
            parts=[]
            for ordinal,(day,amount) in enumerate(sorted(counts.items())):
                parts.append(sample(args.seed+ordinal*130363+2,amount,policy,day,args.year,return_dates=True))
            partitions[name]=tuple(np.concatenate([x[i] for x in parts]) for i in range(4))
    observations=[]; roles=[]; actions=[]; labels=[]; split_indices={}; split_date_names={}; cursor=0
    for name in ('train','validation','test'):
        x,r,y,d=partitions[name]; observations.append(x);roles.append(r);actions.append(y);labels.append(d)
        split_indices[name]=torch.arange(cursor,cursor+len(r),dtype=torch.int64)
        split_date_names[name]=sorted(set(d.tolist()))
        cursor+=len(r)
    all_dates=np.concatenate(labels)
    assert demo_date.isoformat() not in split_date_names['train']
    assert demo_date.isoformat() not in split_date_names['validation']
    assert demo_date.isoformat() in split_date_names['test']
    assert not(set(split_date_names['train']) & set(split_date_names['validation']))
    assert not(set(split_date_names['train']) & set(split_date_names['test']))
    assert not(set(split_date_names['validation']) & set(split_date_names['test']))
    new_data={'observations':torch.from_numpy(np.concatenate(observations)),'roles':torch.from_numpy(np.concatenate(roles)),'actions':torch.from_numpy(np.concatenate(actions)),'dates':all_dates.tolist(),'train_indices':split_indices['train'],'validation_indices':split_indices['validation'],'test_indices':split_indices['test'],'date_splits':split_date_names,'demo_date':demo_date.isoformat(),'weather_year':args.year,'seed':args.seed,'dagger_rounds':args.dagger_rounds}
    if args.append and path.exists():
        old=torch.load(path,map_location='cpu',weights_only=True)
        if 'dates' not in old or old.get('demo_date')!=new_data['demo_date']: parser.error('--append requires an existing date-split dataset with the same demo date; regenerate the dataset instead')
        # Safe append preserves date-group partitions and rejects any date split overlap.
        for key in ('observations','roles','actions'): new_data[key]=torch.cat((old[key],new_data[key]))
        new_data['dates']=list(old['dates'])+new_data['dates']
        for split in ('train','validation','test'):
            old_idx=old[f'{split}_indices']; offset=len(old['roles']); new_idx=new_data[f'{split}_indices']+offset
            new_data[f'{split}_indices']=torch.cat((old_idx,new_idx))
            new_data['date_splits'][split]=sorted(set(old['date_splits'][split]+new_data['date_splits'][split]))
        assert new_data['demo_date'] not in new_data['date_splits']['train']
    torch.save(new_data,path)
    print(f'Wrote {len(new_data["roles"])} date-grouped samples to {path}; train={len(split_indices["train"])} validation={len(split_indices["validation"])} test={len(split_indices["test"])} demo_date={demo_date} weather={"PVGIS cache" if provider else "synthetic fallback"}')

if __name__=='__main__': main()
