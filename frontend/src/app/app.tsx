import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { bootstrapAuth } from '@/lib/auth';
import { router } from './router';

function App() {
  useEffect(() => {
    bootstrapAuth();
  }, []);

  return <RouterProvider router={router} />;
}

export default App;
