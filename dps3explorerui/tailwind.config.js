/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        sidebar: {
          DEFAULT: "var(--sidebar)",
          foreground: "var(--sidebar-foreground)",
          primary: "var(--sidebar-primary)",
          "primary-foreground": "var(--sidebar-primary-foreground)",
          accent: "var(--sidebar-accent)",
          "accent-foreground": "var(--sidebar-accent-foreground)",
          border: "var(--sidebar-border)",
          ring: "var(--sidebar-ring)",
        },
        "new-bg": "var(--new-bg)",
        "new-bg-light": "var(--new-bg-light)",
        "new-button-bg": "var(--new-button-bg)",
        "new-table-header-bg": "var(--new-table-header-bg)",
        "delete-button-bg": "var(--delete-button-bg)",
        "dp-default": "var(--default)",
        "dp-default-light": "var(--default-light)",
        "custom-gray": "var(--custom-gray)",
        "custom-gray-light": "var(--custom-gray-light)",
        "custom-green": "var(--custom-green)",
        "custom-green-medium": "var(--custom-green-medium)",
        "custom-green-light": "var(--custom-green-light)",
        "black-alpha": "var(--black-alpha)",
      },
      boxShadow: {
        "hover-button": "0px 0px 4px 4px rgba(0, 0, 0, 0.1)",
      },
    },
  },
  plugins: [],
};
