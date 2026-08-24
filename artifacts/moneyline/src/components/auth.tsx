import { useEffect, useRef, useState } from 'react';
import { useLocation, useSearchParams } from 'wouter';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError, googleSignInUrl, useAuthActions, useSession } from '@/api';

type Mode = 'login' | 'signup' | 'forgot' | 'reset';
const safePath = (value: string | null) => value?.startsWith('/') && !value.startsWith('//') ? value : '/';

function ErrorText({ children }: { children: React.ReactNode }) {
  return <p role="alert" className="mt-2 text-xs leading-5 text-destructive">{children}</p>;
}

function AuthForm({ mode, onMode, returnTo }: { mode: Mode; onMode: (m: Mode) => void; returnTo: string }) {
  const actions = useAuthActions();
  const [, navigate] = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const [success, setSuccess] = useState('');
  const [params] = useSearchParams();
  const token = params.get('token') || params.get('reset_token');
  const active = mode === 'login' ? actions.login : mode === 'signup' ? actions.signup : mode === 'forgot' ? actions.forgotPassword : actions.resetPassword;
  const busy = active.isPending;
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => { firstField.current?.focus(); }, [mode]);
  useEffect(() => {
    if (params.get('auth_error')) setLocalError('Google sign-in could not be completed. Please try again.');
  }, [params]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault(); setLocalError(''); setSuccess('');
    if (!email && mode !== 'reset') return setLocalError('Enter your email address.');
    if (mode !== 'forgot' && mode !== 'reset' && password.length < 8) return setLocalError('Password must be at least 8 characters.');
    if (mode === 'signup' && !name.trim()) return setLocalError('Enter your name.');
    if (mode === 'reset' && (!token || password.length < 8 || password !== confirm)) {
      return setLocalError(!token ? 'This reset link is missing or invalid.' : password !== confirm ? 'Passwords do not match.' : 'New password must be at least 8 characters.');
    }
    const payload = mode === 'reset' ? { token: token!, password } : mode === 'signup' ? { email, password, name } : mode === 'forgot' ? { email } : { email, password };
    active.mutate(payload as unknown as Record<string, string>, {
      onSuccess: () => {
        if (mode === 'login' || mode === 'signup') navigate(returnTo);
        else if (mode === 'forgot') setSuccess('If an account matches that email, we’ll send reset instructions shortly.');
        else { setSuccess('Your password has been updated. You can now sign in.'); onMode('login'); }
      },
      onError: (error) => setLocalError(error instanceof ApiError && error.status >= 500 ? 'The service is temporarily unavailable. Please try again.' : mode === 'login' ? 'Email or password is incorrect.' : 'We couldn’t complete that request. Please check your details and try again.'),
    });
  };

  const title = mode === 'login' ? 'Sign in to MONEYLINE' : mode === 'signup' ? 'Create your account' : mode === 'forgot' ? 'Reset your password' : 'Set a new password';
  return <Card className="w-full max-w-md border-border bg-card shadow-2xl shadow-black/30">
    <CardHeader className="space-y-3 p-6 sm:p-8">
      <div className="eyebrow text-success">BASEBALL RESEARCH DESK</div>
      <CardTitle className="text-2xl tracking-tight">{title}</CardTitle>
      <CardDescription>{mode === 'login' ? 'Transparent prices, matchups, and paper-pick performance.' : mode === 'signup' ? 'Create a free account to access the full research desk.' : mode === 'forgot' ? 'Enter your email and we’ll send reset instructions if an account matches.' : 'Choose a strong password for your MONEYLINE account.'}</CardDescription>
    </CardHeader>
    <CardContent className="p-6 pt-0 sm:p-8 sm:pt-0">
      {mode === 'reset' && !token ? <ErrorText>This reset link is missing or expired. Request a new link below.</ErrorText> : <>
        {mode === 'login' || mode === 'signup' ? <a href={googleSignInUrl(returnTo)} className="moneyline-focus-ring flex h-10 w-full items-center justify-center gap-2 border border-border bg-background px-4 text-xs font-mono uppercase tracking-wide hover:border-primary"><span className="text-base font-sans">G</span> Continue with Google</a> : null}
        {(mode === 'login' || mode === 'signup') && <div className="my-5 flex items-center gap-3 text-[10px] uppercase tracking-widest text-muted-foreground"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>}
        <form onSubmit={submit} className="space-y-4" noValidate>
          {mode === 'signup' && <div><Label htmlFor="name">Name</Label><Input ref={firstField} id="name" value={name} onChange={e => setName(e.target.value)} autoComplete="name" className="mt-2" /></div>}
          {mode !== 'reset' && <div><Label htmlFor="email">Email address</Label><Input ref={mode === 'login' || mode === 'forgot' ? firstField : undefined} id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" className="mt-2" /></div>}
          {mode !== 'forgot' && <div><div className="flex items-center justify-between"><Label htmlFor="password">{mode === 'reset' ? 'New password' : 'Password'}</Label>{mode === 'login' && <button type="button" onClick={() => onMode('forgot')} className="moneyline-focus-ring text-xs text-muted-foreground hover:text-primary">Forgot password?</button>}</div><div className="relative mt-2"><Input ref={mode === 'signup' || mode === 'reset' ? firstField : undefined} id="password" type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === 'reset' ? 'new-password' : mode === 'signup' ? 'new-password' : 'current-password'} className="pr-20" /><button type="button" onClick={() => setShowPassword(v => !v)} className="moneyline-focus-ring absolute right-2 top-1/2 -translate-y-1/2 px-1 text-[10px] uppercase text-muted-foreground">{showPassword ? 'Hide' : 'Show'}</button></div></div>}
          {mode === 'reset' && <div><Label htmlFor="confirm">Confirm new password</Label><Input id="confirm" type={showPassword ? 'text' : 'password'} value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" className="mt-2" /></div>}
          {localError && <ErrorText>{localError}</ErrorText>}{success && <p role="status" className="text-xs leading-5 text-success">{success}</p>}
          <Button disabled={busy || (mode === 'reset' && !token)} className="h-10 w-full">{busy ? 'Working…' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account' : mode === 'forgot' ? 'Send reset link' : 'Update password'}</Button>
        </form>
      </>}
      <div className="mt-6 text-center text-xs text-muted-foreground">{mode === 'login' ? <>New to MONEYLINE? <button className="moneyline-focus-ring text-primary hover:underline" onClick={() => onMode('signup')}>Create an account</button></> : mode === 'signup' ? <>Already have an account? <button className="moneyline-focus-ring text-primary hover:underline" onClick={() => onMode('login')}>Sign in</button></> : <button className="moneyline-focus-ring text-primary hover:underline" onClick={() => onMode('login')}>Back to sign in</button>}</div>
    </CardContent>
  </Card>;
}

export function AuthScreen({ returnTo, serverError = false }: { returnTo: string; serverError?: boolean }) {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>(params.get('token') || params.get('reset_token') ? 'reset' : 'login');
  return <main className="auth-page min-h-[100dvh] overflow-y-auto bg-background px-4 py-8 sm:px-6"><div className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-6xl items-center justify-center"><div className="w-full"><div className="mb-8 text-center"><div className="text-xl font-bold tracking-tight">MONEYLINE <span className="text-success">●</span></div><p className="mt-2 font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Evidence over instinct</p></div>{serverError && <p role="alert" className="mx-auto mb-4 max-w-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-center text-xs text-destructive">We couldn’t check your session. Please try again.</p>}<AuthForm mode={mode} onMode={setMode} returnTo={returnTo} /></div></div></main>;
}