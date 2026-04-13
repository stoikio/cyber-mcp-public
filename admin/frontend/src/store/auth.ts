import { create } from 'zustand';

interface AuthState {
  token: string | null;
  email: string | null;
  login: (token: string, email: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: sessionStorage.getItem('admin_token'),
  email: sessionStorage.getItem('admin_email'),

  login: (token, email) => {
    sessionStorage.setItem('admin_token', token);
    sessionStorage.setItem('admin_email', email);
    set({ token, email });
  },

  logout: () => {
    sessionStorage.removeItem('admin_token');
    sessionStorage.removeItem('admin_email');
    set({ token: null, email: null });
  },
}));
