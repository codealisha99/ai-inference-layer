import { defineRailway, github, project, service } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "api";
export default defineRailway(() => {
  const api = service("api", {
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    source: github("codealisha99/ai-inference-layer", { branch: "main", checkSuites: false }),
    healthcheck: "/readyz",
    healthcheckTimeout: 120,
    replicas: { "asia-southeast1-eqsg3a": 1 },
  });

  return project("ai-inference-layer", {
    variables: { managed: false },
    resources: [api],
  });
});
