import { Skeleton } from "@/components/ui/skeleton";

export default function EmpresaDetailLoading() {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-12 sm:px-6 lg:px-10">
      <div className="space-y-6">
        <div className="space-y-4">
          <Skeleton className="h-4 w-40 rounded-full" />
          <Skeleton className="h-12 w-2/3 rounded-2xl" />
          <Skeleton className="h-5 w-1/2 rounded-full" />
        </div>
        <Skeleton className="h-40 rounded-3xl" />
      </div>
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-10 w-36 rounded-full" />
        <Skeleton className="h-10 w-36 rounded-full" />
      </div>
      <Skeleton className="h-16 rounded-[1.25rem]" />
      <div className="flex flex-wrap gap-2">
        <Skeleton className="h-9 w-20 rounded-full" />
        <Skeleton className="h-9 w-20 rounded-full" />
        <Skeleton className="h-9 w-20 rounded-full" />
        <Skeleton className="h-9 w-20 rounded-full" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
      </div>
      <div className="space-y-3">
        <Skeleton className="h-10 w-72 rounded-full" />
        <Skeleton className="h-[26rem] rounded-3xl" />
      </div>
    </div>
  );
}
