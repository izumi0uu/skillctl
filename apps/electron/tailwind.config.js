/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/renderer/index.html", "./src/renderer/src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"SF Pro Rounded"', "ui-rounded", '"Varela Round"', "system-ui", "sans-serif"],
        sans: ['"SF Pro Rounded"', "ui-rounded", "system-ui", "sans-serif"],
      },
      colors: {
        cream: "#FFF8EF",
        cloud: "#FFFFFF",
        ink: { DEFAULT: "#3B3640", soft: "#9C95A6" },
        blue: { DEFAULT: "#4C8DFF", ring: "#CBE0FF" },
        mint: { DEFAULT: "#22C7A0", ring: "#BFEFE3" },
        grape: { DEFAULT: "#9B7BFF", ring: "#E3D8FF" },
        lemon: { DEFAULT: "#F7B82E", ring: "#FFE9AE" },
        pink: { DEFAULT: "#FF7BAC", ring: "#FFD6E6" },
        sky: { DEFAULT: "#38C6F4", ring: "#C7ECFF" },
        red: { DEFAULT: "#FB6B6B", ring: "#FFD0D0" },
      },
      boxShadow: {
        puff: "0 12px 26px -12px rgba(59, 54, 64, 0.35)",
        "puff-sm": "0 8px 18px -10px rgba(59, 54, 64, 0.30)",
      },
      borderRadius: {
        chunk: "24px",
        blob: "30px",
      },
      keyframes: {
        jello: {
          "0%,100%": { transform: "scale3d(1,1,1)" },
          "30%": { transform: "scale3d(0.75,1.25,1)" },
          "40%": { transform: "scale3d(1.25,0.75,1)" },
          "50%": { transform: "scale3d(0.85,1.15,1)" },
          "65%": { transform: "scale3d(1.05,0.95,1)" },
          "75%": { transform: "scale3d(0.95,1.05,1)" },
        },
        "pop-in": {
          "0%": { transform: "scale(.9)", opacity: "0" },
          "60%": { transform: "scale(1.03)" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
        "bounce-soft": {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-5px)" },
        },
        float: {
          "0%,100%": { transform: "translateY(0) rotate(-4deg)" },
          "50%": { transform: "translateY(-5px) rotate(4deg)" },
        },
        "slide-up": {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        flow: {
          to: { backgroundPositionX: "18px" },
        },
        indeterminate: {
          "0%": { left: "-40%", width: "40%" },
          "100%": { left: "100%", width: "40%" },
        },
      },
      animation: {
        jello: "jello 0.8s both",
        "pop-in": "pop-in .2s ease-out",
        "bounce-soft": "bounce-soft .6s ease-in-out infinite",
        float: "float 3.5s ease-in-out infinite",
        "slide-up": "slide-up .22s ease-out",
        flow: "flow .5s linear infinite",
        indeterminate: "indeterminate 1.1s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
