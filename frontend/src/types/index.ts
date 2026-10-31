export type AgentStatus = 'Active'|'Paused'|'Needs attention';
export interface Home { id:string; residentName:string; solar:number; solarCapacity:number; demand:number; battery:number; batteryCapacity:number; ev:boolean; evDeadline:string; ac:boolean; status:AgentStatus; action:string; reserve:number; temperature:number; flexibleLoads:string[]; constraints:string[]; recent:string[] }
export interface HomeAgent { homeId:string; status:AgentStatus; currentAction:string; lastUpdated:string }
export interface SocietyAgent { status:AgentStatus; coordinatedHomes:number; currentAction:string }
export interface GridAgent { status:AgentStatus; condition:'Normal'|'High Demand'|'Critical Demand'; pricePerKwh:number; message:string }
export interface EnergyTrade { id:string; fromHome:string; toHome:string; energyKwh:number; status:string; explanation:string; simulated:true }
export interface AgentActivity { time:string; agent:string; type:string; action:string; reason:string; status:string }
export interface SimulationConfig { scenario:string; demand:number; solar:number; speed:number }
export interface SimulationMetrics { demand:number; solar:number; gridImport:number; battery:number; activeAgents:number; gridState:string; price:number; peakReduction:number; savings:number }
export interface SimulationResult { id:string; status:string; config:SimulationConfig; metrics:SimulationMetrics }
export interface ResidentPreference { homeId:string; reserve:number; temperature:number; evDeadline:string; criticalLoads:string; flexibleLoads:string; saving:boolean; instruction:string }
