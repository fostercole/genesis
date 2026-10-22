import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { installDogfood } from "./controller.ts";

export default function (pi: ExtensionAPI) {
  installDogfood(pi, Type.Object({}));
}
