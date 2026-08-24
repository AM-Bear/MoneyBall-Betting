import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useSearchParams } from 'wouter';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError, googleSignInUrl, useAuthActions, useSession } from '@/api';

type Mode = 'login' | 'signup' | 'forgot' | 'reset';
const safePath = (value: string | null) => value?.startsWith('/') && !value.startsWith('//') ? value : '/';

function ErrorText({ children }: { children: ReactNode }) {
  return <p role="alert" className="auth-message auth-message-error">{children}</p>;
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
  const authError = params.get('auth_error');
  useEffect(() => {
    if (authError) setLocalError('Google sign-in could not be completed. Please try again.');
  }, [authError]);

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
  return <Card className="auth-card">
    <CardHeader className="auth-card-header">
      <div className="eyebrow text-success">ACCOUNT ACCESS / {mode === 'login' ? 'SIGN IN' : mode === 'signup' ? 'NEW ACCOUNT' : mode === 'forgot' ? 'RECOVERY' : 'PASSWORD UPDATE'}</div>
      <CardTitle className="auth-card-title">{title}</CardTitle>
      <CardDescription className="auth-card-description">{mode === 'login' ? 'Transparent prices, matchups, and paper-pick performance.' : mode === 'signup' ? 'Create a free account to access the full research desk.' : mode === 'forgot' ? 'Enter your email and we’ll send reset instructions if an account matches.' : 'Choose a strong password for your MONEYLINE account.'}</CardDescription>
    </CardHeader>
    <CardContent className="auth-card-content">
      {mode === 'reset' && !token ? <ErrorText>This reset link is missing or expired. Request a new link below.</ErrorText> : <>
        {mode === 'login' || mode === 'signup' ? <a href={googleSignInUrl(returnTo)} className="auth-social moneyline-focus-ring"><span aria-hidden="true" className="auth-google-mark">G</span> Continue with Google</a> : null}
        {(mode === 'login' || mode === 'signup') && <div className="auth-divider"><span />or<span /></div>}
        <form onSubmit={submit} className="auth-form" noValidate>
          {mode === 'signup' && <div className="auth-field"><Label htmlFor="name">Name</Label><Input ref={firstField} id="name" value={name} onChange={e => setName(e.target.value)} autoComplete="name" className="auth-input" /></div>}
          {mode !== 'reset' && <div className="auth-field"><Label htmlFor="email">Email address</Label><Input ref={mode === 'login' || mode === 'forgot' ? firstField : undefined} id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" className="auth-input" /></div>}
          {mode !== 'forgot' && <div className="auth-field"><div className="flex items-center justify-between gap-3"><Label htmlFor="password">{mode === 'reset' ? 'New password' : 'Password'}</Label>{mode === 'login' && <button type="button" onClick={() => onMode('forgot')} className="moneyline-focus-ring auth-inline-link">Forgot password?</button>}</div><div className="relative"><Input ref={mode === 'signup' || mode === 'reset' ? firstField : undefined} id="password" type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} autoComplete={mode === 'reset' ? 'new-password' : mode === 'signup' ? 'new-password' : 'current-password'} className="auth-input pr-20" /><button type="button" aria-pressed={showPassword} onClick={() => setShowPassword(v => !v)} className="moneyline-focus-ring auth-password-toggle">{showPassword ? 'Hide' : 'Show'}</button></div></div>}
          {mode === 'reset' && <div className="auth-field"><Label htmlFor="confirm">Confirm new password</Label><Input id="confirm" type={showPassword ? 'text' : 'password'} value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" className="auth-input" /></div>}
          {localError && <ErrorText>{localError}</ErrorText>}{success && <p role="status" aria-live="polite" className="auth-message auth-message-success">{success}</p>}
          <Button disabled={busy || (mode === 'reset' && !token)} className="auth-submit">{busy ? 'Working…' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account' : mode === 'forgot' ? 'Send reset link' : 'Update password'}</Button>
        </form>
      </>}
      <div className="auth-mode-switch">{mode === 'login' ? <>New to MONEYLINE? <button type="button" className="moneyline-focus-ring auth-inline-link text-primary" onClick={() => onMode('signup')}>Create an account</button></> : mode === 'signup' ? <>Already have an account? <button type="button" className="moneyline-focus-ring auth-inline-link text-primary" onClick={() => onMode('login')}>Sign in</button></> : <button type="button" className="moneyline-focus-ring auth-inline-link text-primary" onClick={() => onMode('login')}>Back to sign in</button>}</div>
    </CardContent>
  </Card>;
}

export function AuthScreen({ returnTo, serverError = false }: { returnTo: string; serverError?: boolean }) {
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>(params.get('token') || params.get('reset_token') ? 'reset' : 'login');
  return <main className="auth-page"><div className="auth-shell">
    <section className="auth-brief" aria-labelledby="auth-brand">
      <div className="auth-brand-lockup"><div id="auth-brand" className="auth-wordmark">MONEYLINE <span aria-hidden="true" className="auth-status-dot" /></div><p className="auth-kicker">Evidence over instinct</p></div>
      <div className="auth-brief-copy"><div className="eyebrow text-success">BASEBALL RESEARCH DESK</div><h1>Make the line earn your attention.</h1><p>See the price, the matchup, and the record behind every paper pick—without the noise.</p></div>
      <div className="auth-readout" aria-label="MONEYLINE desk readout"><div className="auth-readout-heading"><span>DESK READOUT</span><span className="auth-live-mark"><i /> READY</span></div><div className="auth-readout-row"><span>MODEL</span><strong>TRANSPARENT</strong></div><div className="auth-readout-row"><span>PRICE</span><strong>DISCLOSED</strong></div><div className="auth-readout-row"><span>RECEIPT</span><strong>TRACKED</strong></div></div>
      <p className="auth-brief-footnote">A clear line starts with a clear record.</p>
    </section>
    <section className="auth-form-column" aria-label="Account access">
      <div className="auth-mobile-brand"><div className="auth-wordmark">MONEYLINE <span aria-hidden="true" className="auth-status-dot" /></div><p className="auth-kicker">Evidence over instinct</p></div>
      {serverError && <p role="alert" className="auth-server-error">We couldn’t check your session. Please try again.</p>}
      <AuthForm mode={mode} onMode={setMode} returnTo={returnTo} />
      <p className="auth-legal">Private research desk access. No noise, no hype.</p>
    </section>
  </div></main>;
}