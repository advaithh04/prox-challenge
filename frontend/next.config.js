/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: process.env.NEXT_PUBLIC_API_URL
          ? `${process.env.NEXT_PUBLIC_API_URL}/api/:path*`
          : 'https://prox-challenge-production-a6f9.up.railway.app/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
// Vercel rebuild Sat Apr 11 19:43:32 EDT 2026
