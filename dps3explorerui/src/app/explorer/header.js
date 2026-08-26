import Image from "next/image";
import Logo from "../assets/dplogo.svg";
export default function Header({ children }) {
  return (
    <div className="bg-gray-25 fixed row-start-1 w-full h-25 z-20 border-b border-gray-200">
      <div className="flex flex-row justify-between my-5">
        {/* <p className="mx-4">logo</p> */}
        <div className="pl-10">
          <Image src={Logo} height={50} alt="Explorer logo" />
        </div>
        <input
          className="border-0 py-1.5 pl-7 rounded-md pr-20 ring-1 ring-inset ring-black focus:ring-gray-400 placeholder:text-gray-400 focus:ring-2 focus:ring-inset min-w-0"
          type="text"
          autoComplete="text"
          placeholder="Search.."
        />
        <p className="mx-4">Options</p>
      </div>
    </div>
  );
}
