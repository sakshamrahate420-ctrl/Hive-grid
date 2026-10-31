import { useEffect, useRef, useState } from 'react';
import { Bell, Check, ChevronRight } from 'lucide-react';
import type { AppNotification } from '../types/notifications';
import type { UserRole } from '../types/portal';
import { notificationService } from '../services/notificationService';

export function NotificationBell({role,userKey,homeId,refreshKey,onAction}:{role:UserRole;userKey:string;homeId?:string;refreshKey:string;onAction?:(target:string)=>void}){
 const [open,setOpen]=useState(false);const [items,setItems]=useState<AppNotification[]>([]);const root=useRef<HTMLDivElement>(null);
 const refresh=()=>setItems(notificationService.list(role,userKey,homeId));
 useEffect(()=>{refresh()},[role,userKey,homeId,refreshKey]);
 useEffect(()=>{if(!open)return;const close=(event:MouseEvent)=>{if(root.current&&!root.current.contains(event.target as Node))setOpen(false)};const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false)};document.addEventListener('mousedown',close);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',escape)}},[open]);
 const unread=items.filter(item=>item.unread).length;
 function openItem(item:AppNotification){if(item.unread){notificationService.markRead(userKey,item.id);refresh()}if(item.actionTarget)onAction?.(item.actionTarget);setOpen(false)}
 function markAll(){notificationService.markAllRead(userKey,items.map(item=>item.id));refresh()}
 return <div className="notification-bell" ref={root}><button className="icon-btn notify" aria-label={unread?`Notifications, ${unread} unread`:'Notifications'} aria-expanded={open} onClick={()=>{refresh();setOpen(value=>!value)}}><Bell size={19}/>{unread>0&&<i className="notification-count">{unread>9?'9+':unread}</i>}</button>{open&&<section className="notification-popover" role="dialog" aria-label="Notifications"><div className="notification-popover-head"><div><h2>Notifications</h2><small>{unread?`${unread} unread`:'You are up to date'}</small></div><button className="mark-read-btn" disabled={!unread} onClick={markAll}><Check size={14}/> Mark all read</button></div><div className="notification-popover-list">{items.length===0&&<p className="notification-empty">No notifications yet.</p>}{items.map(item=><button className={`notification-item ${item.unread?'unread':''}`} key={item.id} onClick={()=>openItem(item)}><span className={`notification-indicator ${item.unread?'new':''}`}/><span className="notification-item-copy"><span className="notification-item-title">{item.title}</span><span className="notification-item-message">{item.message}</span><span className="notification-item-meta">{item.kind} · {item.timestamp}</span>{item.actionLabel&&<span className="notification-item-action">{item.actionLabel}<ChevronRight size={13}/></span>}</span></button>)}</div></section>}</div>
}
