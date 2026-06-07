/** @module LoginPage — Username/password sign-in that establishes the session cookie. */
"use client";

import axios from "axios";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import logo from "@/../assets/logo.png";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { login } from "@/lib/api";
import { setUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/**
 * Public sign-in page. On success the backend sets the session and CSRF cookies,
 * the current user is stored in the auth slice, and the user is sent to the chat.
 */
export default function LoginPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const onSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setPending(true);
      try {
        const user = await login(username, password);
        dispatch(setUser(user));
        router.replace("/new-session");
      } catch (err) {
        setError(
          axios.isAxiosError(err) && err.response?.status === 401
            ? "Invalid username or password."
            : "Something went wrong. Please try again."
        );
        setPending(false);
      }
    },
    [username, password, dispatch, router]
  );

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="glass-panel flex w-full max-w-sm flex-col gap-5 rounded-2xl p-8"
      >
        <div className="flex flex-col items-center gap-3">
          <Image
            src={logo}
            alt="A2Flow logo"
            width={logo.width}
            height={logo.height}
            className="h-12 w-auto"
            priority
          />
          <h1
            className="text-xl font-semibold tracking-tight text-gradient-accent"
            style={{ fontFamily: "var(--font-space-grotesk)" }}
          >
            Sign in to A2Flow
          </h1>
        </div>

        <FormField htmlFor="username" label="Username" required>
          <Input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
          />
        </FormField>

        <FormField htmlFor="password" label="Password" required>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </FormField>

        {error && <p className="text-sm text-error">{error}</p>}

        <Button type="submit" variant="primary" disabled={pending} className="w-full">
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
