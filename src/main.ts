import './lib/styles/tokens.css';
import './lib/styles/base.css';
import './lib/styles/motion.css';
import App from './App.svelte';
import { mount } from 'svelte';

mount(App, { target: document.getElementById('app')! });
