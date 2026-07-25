/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/agent-api/:path*",
        destination: "http://agent:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
