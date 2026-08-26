"use client";
import Image from "next/image";
import { useQuery, useMutation } from "react-query";
import { useContext, useState, useRef, useEffect } from "react";
import ChevronRight from "../app/assets/chevronright.svg";
import { ApplicationContext } from "@/services/ContextProvider";
import HomeIcon from "../app/assets/home.svg";
import { loadContents } from "@/services/Queries";

export default function Ribbon({ children }) {
  const { keys, setKeys, setPath } = useContext(ApplicationContext);

  var [visible, setVisible] = useState(false);
  const toggleView = () => {
    setVisible((visible = !visible));
  };
  return (
    <nav
      className="px-4 mr-4 py-2 w-3/5 text-foreground border border-border rounded-lg bg-secondary"
      aria-label="Breadcrumb"
    >
      <ol className="flex flex-row items-center">
        <Image src={HomeIcon} height="15" alt="Home Icon" />
        {keys.length > 3 ? (
          <div className="">
            <button
              onClick={toggleView}
              className="ml-2 font-bold inline-flex items-center hover:bg-gray-100 hover:text-gray-900 hover:cursor-pointer hover:rounded-md px-3 -my-2"
            >
              ...
            </button>
            <Dropdown
              visible={visible}
              setVisible={setVisible}
              list={keys.slice(0, -3)}
            />
            <Image
              className="ml-2 inline-flex"
              src={ChevronRight}
              alt="chevron-right"
            />
            <BreadCrumb
              items={keys.slice(-3, keys.length)}
              initial={keys.length - 3}
            />
          </div>
        ) : (
          <BreadCrumb items={keys} initial={0} />
        )}
      </ol>
    </nav>
  );
}

function Dropdown({ visible, list, sendData, setVisible }) {
  const { keys, setKeys, path, setPath, basePath, currentOrg } = useContext(ApplicationContext);
  const ref = useRef(null);
  const folderMutation = useMutation({
    mutationFn: (p) => loadContents(p, basePath, currentOrg?.id),
  });
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setVisible((prev) => !prev);
      }
    };
    document.addEventListener("click", handleClickOutside, true);
    return () => {
      document.removeEventListener("click", handleClickOutside, true);
    };
  });
  return (
    <div className="inline-flex">
      {visible && (
        <div
          ref={ref}
          className="z-10 mt-1 absolute bg-popover rounded-lg border border-border shadow-lg"
        >
          <ul className="max-h-[85vh] overflow-y-auto">
            {list.map((data, index) => {
              return (
                <li
                  key={index}
                  onClick={() => {
                    const _k = keys.splice(0, index + 1);
                    setKeys(_k);
                    const _p = _k.join("/") + "/";
                    setPath(_p);
                    folderMutation.mutate(_p);
                  }}
                  className="hover:bg-gray-50 hover:cursor-pointer hover:text-gray-900 rounded-md px-6 py-2.5 text-sm"
                >
                  {data}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function BreadCrumb({ items, initial }) {
  const { keys, setKeys, path, setPath, basePath, currentOrg } = useContext(ApplicationContext);
  const folderMutation = useMutation({
    mutationFn: (p) => loadContents(p, basePath, currentOrg?.id),
  });
  return (
    <div className="inline-flex flex-row">
      {items.map((data, index) => {
        return (
          <li key={index} aria-current="page">
            {index === items.length - 1 ? (
              <div className="flex items-center">
                <span className="ms-1 text-md font-medium text-muted-foreground md:ms-2">
                  {data}
                </span>
              </div>
            ) : (
              <div className="flex max-w-full items-center">
                <a
                  onClick={() => {
                    const _k = keys.splice(0, initial + index + 1);
                    setKeys(_k);
                    const _p = _k.join("/") + "/";
                    setPath(_p);
                    folderMutation.mutate(_p);
                  }}
                  className="ms-1 md:ms-2 text-md font-medium text-gray-500 hover:cursor-pointer hover:text-gray-900"
                >
                  {data}
                </a>
                <Image
                  className="ml-2"
                  src={ChevronRight}
                  alt="chevron-right"
                />
              </div>
            )}
          </li>
        );
      })}
    </div>
  );
}
