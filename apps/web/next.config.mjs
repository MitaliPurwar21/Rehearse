/** @type {import('next').NextConfig} */
const nextConfig = {
  // We lint Python in CI; skip Next's ESLint step so the build doesn't require it.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
