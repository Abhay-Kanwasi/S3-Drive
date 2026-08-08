import Image from "next/image";
import UploadIcon from "../app/assets/bigupload.svg";

export default function DragAndDrop({ children }) {
  return (
    <div className="w-full h-full px-10 py-10 select-none bg-background">
      <div className="border-4 border-dashed border-border rounded-2xl h-full flex flex-col justify-center items-center">
        <Image src={UploadIcon} alt="Upload icon" />
        <p className="font-semibold text-2xl text-muted-foreground mt-4">
          Drag & Drop files here
        </p>
      </div>
    </div>
  );
}
