"use client";
import { useQuery, useQueries } from "react-query";
import Cards from "./cards";
import List from "./list";
import { loadContents, loadFolderitems } from "@/services/Queries";
import { useContext, useEffect } from "react";
import { ApplicationContext } from "@/services/ContextProvider";

export default function View({ children }) {
  const {
    userid,
    path,
    card,
    setDuplicates,
    duplicates,
    trashpath,
    trashView,
    setTrashView,
    basePath,
    currentOrg,
  } = useContext(ApplicationContext);
  const contents = useQuery(
    ["contents", path, currentOrg?.id],
    () => loadContents(path, basePath, currentOrg?.id),
    {
      cacheTime: 3000,
    }
  );
  const trashItems = useQuery(
    ["trash", trashpath, currentOrg?.id],
    () => loadFolderitems(currentOrg?.id),
    {
      cacheTime: 3000,
    }
  );
  useEffect(() => {
    if (contents.data) {
      const _names = [];
      for (let _d of contents.data) {
        _names.push(_d.name);
      }
      setDuplicates(new Set(_names));
    }
  }, [contents.data]);
  if (contents.isLoading && !trashView) {
    return (
      <div className="flex flex-wrap  animate-pulse">
        <div className="flex flex-row justify-center items-center w-40 h-40 mr-6 mt-4 mb-4 bg-gray-300 select-none cursor-pointer border rounded-lg px-6 py-4 duration-200 transition ease-in-out delay-100">
          <span className="text-gray-400"> Loading...</span>
        </div>
      </div>
    );
  }
  if (trashItems.isLoading && trashView) {
    return (
      <div className="flex flex-wrap  animate-pulse">
        <div className="flex flex-row justify-center items-center w-40 h-40 mr-6 mt-4 mb-4 bg-gray-300 select-none cursor-pointer border rounded-lg px-6 py-4 duration-200 transition ease-in-out delay-100">
          <span className="text-gray-400"> Loading...</span>
        </div>
      </div>
    );
  }
  if (contents.isSuccess && !trashView)
    return contents.data.map((data, index) => {
      {
        return card ? (
          <Cards
            key={index}
            name={data.name}
            type={data.type}
            size={data.size}
            last_modified={data.last_modified}
            keypath={data.key}
            created_by_role={data.created_by_role}
            is_own={data.is_own}
          />
        ) : (
          <List
            key={index}
            name={data.name}
            type={data.type}
            size={data.size}
            keypath={data.key}
            last_modified={data.last_modified}
            created_by_role={data.created_by_role}
            is_own={data.is_own}
          />
        );
      }
    });
  if (trashItems.isSuccess && trashView)
    return trashItems.data.map((data, index) => {
      {
        return card ? (
          <Cards
            key={index}
            name={data.name}
            type={data.type}
            size={data.size}
            last_modified={data.last_modified}
            keypath={data.trash_key || data.key}
          />
        ) : (
          <List
            key={index}
            name={data.name}
            type={data.type}
            size={data.size}
            keypath={data.trash_key || data.key}
            last_modified={data.last_modified}
          />
        );
      }
    });
}
