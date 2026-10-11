import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from '../ErrorBoundary';
import HeatmapApp from './HeatmapApp';
import './heatmap.css';

const root = document.getElementById('root');
if (!root) throw new Error('#root element missing from heatmap.html');

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary name="Heatmap">
      <HeatmapApp />
    </ErrorBoundary>
  </StrictMode>,
);
