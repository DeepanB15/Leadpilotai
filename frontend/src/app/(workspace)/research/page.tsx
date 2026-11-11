import JobList from "@/components/research/JobList";

export default function ResearchPage() {
  return (
    <div>
      <h1 className="mb-1 text-lg font-semibold">Research jobs</h1>
      <p className="mb-4 text-sm text-gray-500">Progress, per-source status and errors. Click a row for source details.</p>
      <JobList />
    </div>
  );
}
