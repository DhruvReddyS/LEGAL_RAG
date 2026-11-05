"use client";

import { SupervisorView } from "@/components/police/SupervisorView";
import type { MyUnit } from "@/lib/types-police";
import { PageHead } from "./context";

export default function UnitScreen({ units }: { units: MyUnit[] }) {
  return (
    <div className="pro-page">
      <PageHead title="Unit supervision" lead="Compliance and imminent breaches across the unit you supervise." />
      <SupervisorView units={units} />
    </div>
  );
}
