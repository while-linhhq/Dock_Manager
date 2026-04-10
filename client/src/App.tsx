import React from 'react';
import { AppRouter } from './router';
import './index.css';

const App: React.FC = () => {
  return (
    <React.StrictMode>
      <AppRouter />
    </React.StrictMode>
  );
};

export default App;
