import React, { useState } from 'react';
import { useAuthStore } from '../store/authStore';
import { LoginBranding } from '../components/LoginBranding';
import { LoginCredentialsForm } from '../components/LoginCredentialsForm';

export const LoginView: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { login, isLoading, error } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login(email, password);
    } catch {
      // Error is handled in store
    }
  };

  return (
    <div className="space-y-6">
      <LoginBranding />
      <LoginCredentialsForm
        email={email}
        password={password}
        isLoading={isLoading}
        error={error}
        onEmailChange={setEmail}
        onPasswordChange={setPassword}
        onSubmit={handleSubmit}
      />
    </div>
  );
};
