"""Train HivePolicy from scratch with deterministic teacher imitation."""
import argparse, random
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset
from model import HivePolicy, parameter_count, FEATURES

def _split_data(data: dict, smoke: bool):
    if not all(key in data for key in ('train_indices','validation_indices','test_indices','dates','date_splits','demo_date')):
        raise ValueError('Training requires a date-split dataset from collect.py; regenerate it with a reserved --demo-date.')
    train_idx=data['train_indices'].long(); validation_idx=data['validation_indices'].long(); test_idx=data['test_indices'].long()
    labels=list(data['dates']); demo_date=str(data['demo_date'])
    train_dates={labels[int(i)] for i in train_idx}; validation_dates={labels[int(i)] for i in validation_idx}; test_dates={labels[int(i)] for i in test_idx}
    assert demo_date not in train_dates, 'demo date leaked into training'
    assert demo_date not in validation_dates, 'demo date leaked into validation'
    assert demo_date in test_dates, 'demo date is missing from test'
    assert not(train_dates & validation_dates or train_dates & test_dates or validation_dates & test_dates), 'calendar dates overlap dataset splits'
    return data,train_idx,validation_idx


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--data',default='data/teacher.pt'); parser.add_argument('--output',default='artifacts/hive_policy.pt'); parser.add_argument('--epochs',type=int,default=12); parser.add_argument('--batch-size',type=int,default=128); parser.add_argument('--seed',type=int,default=17); parser.add_argument('--smoke',action='store_true'); args=parser.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed); torch.use_deterministic_algorithms(True)
    if not Path(args.data).exists() and args.smoke:
        from collect import sample
        x,r,y=sample(args.seed,512); data={'observations':torch.from_numpy(x),'roles':torch.from_numpy(r),'actions':torch.from_numpy(y)}; train_idx=validation_idx=None
    else:
        data=torch.load(args.data,map_location='cpu',weights_only=True)
        data,train_idx,validation_idx=_split_data(data,args.smoke)
    if train_idx is None:
        train_indices=torch.arange(min(len(data['roles']),512 if args.smoke else len(data['roles'])))
        validation_indices=torch.empty(0,dtype=torch.int64)
    else:
        train_indices=train_idx; validation_indices=validation_idx
    train_ds=TensorDataset(data['observations'][train_indices],data['roles'][train_indices],data['actions'][train_indices])
    loader=DataLoader(train_ds,batch_size=16 if args.smoke else args.batch_size,shuffle=True,generator=torch.Generator().manual_seed(args.seed))
    model=HivePolicy(); optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4); epochs=1 if args.smoke else args.epochs
    losses=[]; validation_losses=[]
    for epoch in range(epochs):
        total=0.
        for x,role,y in loader:
            optimizer.zero_grad(set_to_none=True); loss=torch.nn.functional.mse_loss(model(x,role),y); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); optimizer.step(); total+=float(loss.detach())
        epoch_mse=total/max(1,len(loader)); losses.append(epoch_mse)
        val_mse=None
        if len(validation_indices):
            val_ds=TensorDataset(data['observations'][validation_indices],data['roles'][validation_indices],data['actions'][validation_indices])
            val_loader=DataLoader(val_ds,batch_size=args.batch_size,shuffle=False)
            total_val=0.; batches=0
            model.eval()
            with torch.inference_mode():
                for x,role,y in val_loader: total_val+=float(torch.nn.functional.mse_loss(model(x,role),y)); batches+=1
            model.train(); val_mse=total_val/max(1,batches); validation_losses.append(val_mse)
        print(f'epoch {epoch+1}/{epochs}: train_mse={epoch_mse:.6f}'+(f' validation_mse={val_mse:.6f}' if val_mse is not None else ''))
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    metadata={'sample_count':len(train_indices),'epochs':epochs,'batch_size':16 if args.smoke else args.batch_size,'final_train_mse':losses[-1],'final_validation_mse':validation_losses[-1] if validation_losses else None}
    if 'demo_date' in data: metadata.update({'demo_date':data['demo_date'],'training_dates':data['date_splits']['train'],'validation_dates':data['date_splits']['validation'],'test_dates':data['date_splits']['test'],'test_samples_not_used_for_training':True})
    torch.save({'state_dict':model.state_dict(),'features':FEATURES,'actions':7,'seed':args.seed,'training':metadata},out)
    print(f'Saved {parameter_count(model):,} parameters to {out}')
if __name__=='__main__': main()
