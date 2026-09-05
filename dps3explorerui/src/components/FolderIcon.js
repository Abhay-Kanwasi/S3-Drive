export default function FolderIcon({ className = "w-9 h-9 shrink-0" }) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M4 11C4 8.79086 5.79086 7 8 7H18.3431C19.404 7 20.4214 7.42143 21.1716 8.17157L24.8284 11.8284C25.5786 12.5786 26.596 13 27.6569 13H40C42.2091 13 44 14.7909 44 17V37C44 39.2091 42.2091 41 40 41H8C5.79086 41 4 39.2091 4 37V11Z"
        fill="#F59E0B"
      />
      <rect x="7" y="14" width="34" height="23" rx="2" fill="#FFFFFF" fillOpacity="0.2" />
      <path
        d="M4 18C4 15.7909 5.79086 14 8 14H40C42.2091 14 44 15.7909 44 18V37C44 39.2091 42.2091 41 40 41H8C5.79086 41 4 39.2091 4 37V18Z"
        fill="#FBBF24"
      />
      <path
        d="M5 19C5 17.3431 6.34315 16 8 16H40C41.6569 16 43 17.3431 43 19V20H5V19Z"
        fill="#FEF08A"
        fillOpacity="0.6"
      />
    </svg>
  );
}
