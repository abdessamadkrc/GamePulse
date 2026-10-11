import './globals.css';
import type { Metadata } from 'next';
import Shell from '@/components/Shell';

export const metadata: Metadata = {
  title: 'GamePulse - Gaming Analytics & Operations',
  description: 'Synthetic portfolio project: analytics and game-operations console for a live-service mobile game. Not affiliated with Garena or Free Fire.',
};

const themeScript = `try{var t=localStorage.getItem('gp-theme');if(t){document.documentElement.setAttribute('data-theme',t)}}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
