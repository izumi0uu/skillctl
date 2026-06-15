import type { SkillctlApi } from "../shared/ipc-contract";

declare global {
  interface Window {
    skillctl: SkillctlApi;
  }
}
