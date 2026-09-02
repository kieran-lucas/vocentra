import { BookOpen, Brain, Languages, Sparkles, Library, GraduationCap, Atom, Target, Layers3, Boxes, NotebookTabs, Lightbulb } from 'lucide-svelte';
export const icons:Record<string,typeof BookOpen>={'book-open':BookOpen,brain:Brain,languages:Languages,sparkles:Sparkles,library:Library,education:GraduationCap,atom:Atom,target:Target,layers:Layers3,boxes:Boxes,notebook:NotebookTabs,idea:Lightbulb};
export const iconOptions=Object.keys(icons);
