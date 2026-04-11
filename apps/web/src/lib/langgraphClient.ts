import { Client } from "@langchain/langgraph-sdk";

const apiUrl =
  import.meta.env.VITE_LANGGRAPH_API_URL ?? "http://localhost:8123";

export const langgraphClient = new Client({ apiUrl });
