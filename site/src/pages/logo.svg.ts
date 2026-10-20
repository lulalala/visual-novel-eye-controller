// Serves the logo as the site icon.
import type { APIRoute } from "astro";
import logo from "../../../logo/eye-blink.svg?raw";

export const GET: APIRoute = () =>
  new Response(logo, { headers: { "Content-Type": "image/svg+xml" } });
