import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Moon, Sun } from 'lucide-react';

export type ThemeMode='light'|'dark'|'system';
const ThemeContext=createContext<{theme:ThemeMode;setTheme:(theme:ThemeMode)=>void}|null>(null);
function storedTheme():ThemeMode{try{const value=localStorage.getItem('hivegrid-theme');return value==='dark'||value==='system'?value:'light'}catch{return 'light'}}
export function ThemeProvider({children}:{children:ReactNode}){const [theme,setTheme]=useState<ThemeMode>(storedTheme);useEffect(()=>{const media=window.matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=theme==='system'?(media.matches?'dark':'light'):theme;localStorage.setItem('hivegrid-theme',theme)};apply();if(theme==='system')media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply)},[theme]);const value=useMemo(()=>({theme,setTheme}),[theme]);return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>}
export function useTheme(){const value=useContext(ThemeContext);if(!value)throw new Error('useTheme must be used within ThemeProvider');return value}
export function ThemeToggle(){const {theme,setTheme}=useTheme();const dark=theme==='dark'||(theme==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);return <button className="icon-btn theme-toggle" aria-label={dark?'Switch to light mode':'Switch to dark mode'} title={dark?'Light mode':'Dark mode'} onClick={()=>setTheme(dark?'light':'dark')}>{dark?<Sun size={18}/>:<Moon size={18}/>}</button>}
