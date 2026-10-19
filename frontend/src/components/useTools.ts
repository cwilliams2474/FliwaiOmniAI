"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ToolSpec } from "@/lib/types";

export function useTools(): ToolSpec[] {
  const [tools, setTools] = useState<ToolSpec[]>([]);
  useEffect(() => { api<ToolSpec[]>("/automation/tools").then(setTools).catch(() => {}); }, []);
  return tools;
}
