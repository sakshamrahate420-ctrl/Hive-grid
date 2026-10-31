import type { SimulationMetrics } from '../types';
export const initialMetrics:SimulationMetrics={demand:184.6,solar:72.4,gridImport:91.2,battery:318.5,activeAgents:53,gridState:'Normal',price:6.8,peakReduction:18,savings:12};
export const timeline=Array.from({length:12},(_,i)=>({time:`${String(8+i).padStart(2,'0')}:00`,demand:95+Math.round(50*Math.sin((i/11)*Math.PI))+i*2,solar:i<2||i>9?8:20+Math.round(42*Math.sin(((i-2)/8)*Math.PI)),baseline:112+Math.round(58*Math.sin((i/11)*Math.PI)),coordinated:95+Math.round(50*Math.sin((i/11)*Math.PI))}));
