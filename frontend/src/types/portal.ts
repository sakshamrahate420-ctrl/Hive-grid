export type UserRole = 'admin'|'resident';
export type RequestStatus = 'Submitted'|'Under Review'|'Approved'|'Rejected'|'Scheduled'|'Applied'|'Cancelled';
export interface ResidentRequest { id:string; homeId:string; resident:string; description:string; date:string; category:string; priority:'Critical'|'Preferred'|'Flexible'; status:RequestStatus; adminResponse:string; updated:string; constraint?:Record<string,number|number[]>; unsupportedFields?:string[]; execution?:{status:string;step:number;time:string;constraint:Record<string,unknown>}|null }
export interface DemoUser { role:UserRole; name:string; email:string; homeId?:string; society:string }
export interface Invitation { id:string; email:string; homeId:string; code:string; status:'Pending'|'Accepted'; created:string }
