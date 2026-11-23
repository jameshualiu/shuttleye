import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar";

export type PrivateLayoutContext = {
  onUploadClick: () => void;
  uploadTrigger: number;
};

export default function PrivateLayout() {
  const [uploadTrigger, setUploadTrigger] = useState(0);

  const handleUploadClick = () => {
    setUploadTrigger((prev) => prev + 1);
  };

  return (
    <div className="flex min-h-screen bg-background text-foreground max-lg:flex-col">
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">
        <Outlet
          context={{
            onUploadClick: handleUploadClick,
            uploadTrigger,
          }}
        />
      </div>
    </div>
  );
}
