import '../styles/base.css';
import '../styles/console.css';
import Shell from '@/components/Shell';

export const metadata = {
  title: 'Quillon Medical Information',
  robots: 'noindex',
  icons: { icon: '/favicon.svg' },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
