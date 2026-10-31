"""Reward-weighted on-policy fine-tuning of the HOME policy head."""
import argparse, random
from pathlib import Path
import numpy as np
import torch
from model import HivePolicy, ROLE_HOME, FEATURES
from collect import sample

# Action dimensions are fractions of each device's rated capacity (see collect.py):
# [ac/6kW, ev/8kW, geyser/1.2kW, other/1kW, battery_charge/3kW, battery_discharge/3kW, comfort_deficit/10C]
DEVICE_SCALES = (6.0, 8.0, 1.2, 1.0, 3.0, 3.0, 10.0)

def _to_tensor(value: torch.Tensor | np.ndarray) -> torch.Tensor:
    return value if isinstance(value, torch.Tensor) else torch.from_numpy(value)

def reward(actions: torch.Tensor, observations: torch.Tensor) -> torch.Tensor:
    """Per-step utility from grid import cost, stress-window peaks, and comfort deficits.

    ``actions`` is [..., 7] in normalized units (fractions of the nominal maxima used
    by collect.py). ``observations`` is [..., FEATURES] or [..., steps, FEATURES];
    when actions lack a step axis they are broadcast across all steps.
    """
    scales = torch.tensor(DEVICE_SCALES, dtype=torch.float32)
    if actions.dim() == observations.dim() - 1:  # one action vector per sequence -> broadcast over steps
        actions = actions.unsqueeze(-2).expand(*observations.shape[:-1], actions.shape[-1])
    kw = actions.clamp(0, 1) * scales                     # controllable loads in kW / deficit in deg C
    ac, ev, geyser, other, charge, discharge, comfort = (t.unsqueeze(-1) for t in kw.unbind(-1))  # [..., steps, 1]
    price = observations[..., 4].clamp(0, 1).unsqueeze(-1); stress = observations[..., 5].clamp(0, 1).unsqueeze(-1); solar = (observations[..., 3].clamp(0, 1) * scales[1]).unsqueeze(-1)
    base_load = (observations[..., 11] * scales[3]).unsqueeze(-1)  # fixed base load feature in kW
    import_kw = (base_load + ac + ev + geyser + other + charge - discharge - solar).clamp(min=0)
    cost = import_kw * price
    peak = (import_kw * (.5 + stress)).square()
    comfort_penalty = comfort.clamp(min=0).square()
    violation = (torch.relu(actions - 1) + torch.relu(-actions)).square().sum(dim=-1, keepdim=True)
    return -(cost + .25 * peak + .35 * comfort_penalty + 3 * violation)

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--model',default='artifacts/hive_policy.pt'); parser.add_argument('--data',default='data/teacher.pt'); parser.add_argument('--output',default='artifacts/hive_policy_rl.pt'); parser.add_argument('--updates',type=int,default=200); parser.add_argument('--seed',type=int,default=29); parser.add_argument('--smoke',action='store_true'); args=parser.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed); torch.use_deterministic_algorithms(True)
    if Path(args.model).exists():
        saved=torch.load(args.model,map_location='cpu',weights_only=True); model=HivePolicy(); model.load_state_dict(saved['state_dict'])
    elif args.smoke:
        model=HivePolicy()
    else: raise SystemExit(f'Missing trained imitation model: {args.model}; train.py must run first')
    if args.smoke:  # tiny cold-start path: quick one-step fit, then fine-tune on freshly sampled data
        x,r,y=sample(args.seed,128); optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4)
        ox=torch.from_numpy(x); rr=torch.from_numpy(r); yy=torch.from_numpy(y)
        optimizer.zero_grad(set_to_none=True); torch.nn.functional.mse_loss(model(ox,rr),yy).backward(); optimizer.step()
        data={'observations':ox,'roles':rr,'actions':yy}
    else: data=torch.load(args.data,map_location='cpu',weights_only=True)
    observations=_to_tensor(data['observations'])[(_to_tensor(data['roles']))==ROLE_HOME]
    if len(observations)==0: raise SystemExit('Training data has no HOME role samples')
    for parameter in model.parameters(): parameter.requires_grad_(False)
    home_head=model.heads[ROLE_HOME]
    for parameter in home_head.parameters(): parameter.requires_grad_(True)
    optimizer=torch.optim.AdamW(home_head.parameters(),lr=1e-5); updates=2 if args.smoke else args.updates; batch_size=8 if args.smoke else 32
    for update in range(updates):
        indices=torch.randint(len(observations),(batch_size,)); obs=observations[indices]
        encoded=model.norm(model.encoder(model.input(obs)+model.position[:,:obs.shape[1]]+model.role(torch.full((batch_size,),ROLE_HOME,dtype=torch.long)).unsqueeze(1)).mean(dim=1))
        mean=home_head(encoded); dist=torch.distributions.Normal(mean.clamp(0,1),torch.full_like(mean,.12)); action=dist.rsample().clamp(0,1); log_prob=dist.log_prob(action).sum(-1)
        returns=reward(action,obs).mean(dim=1); advantage=(returns-returns.mean()).detach()
        loss=-(log_prob*advantage).mean() + .01*(mean.square().mean())
        optimizer.zero_grad(set_to_none=True); loss.backward(); torch.nn.utils.clip_grad_norm_(home_head.parameters(),.5); optimizer.step()
        if update % max(1,updates//5)==0: print(f'update {update+1}/{updates}: reward={returns.mean().item():.4f} loss={loss.item():.4f}')
    target=Path(args.output); target.parent.mkdir(parents=True,exist_ok=True); torch.save({'state_dict':model.state_dict(),'features':FEATURES,'actions':7,'seed':args.seed,'fine_tuned':'home_reward_policy'},target); print(f'Saved fine-tuned HOME head to {target}')
if __name__=='__main__': main()
