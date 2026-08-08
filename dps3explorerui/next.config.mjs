/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  basePath: '/explorer',
  async headers() {
    return [
      {
        source: "/(.*)?",
        headers: [
          {
            key: "Access-Control-Allow-Origin",
            value: "*",
          },
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors https://green.datapoem.ai https://qa.datapoem.ai https://devapp.datapoem.ai https://qaapp.datapoem.ai https://app.datapoem.ai https://insights.datapoem.ai http://localhost:8080",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
