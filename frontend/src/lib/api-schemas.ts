// Friendly aliases for the backend response/request models, sourced from the
// generated OpenAPI types (src/lib/api-types.ts). Import these in pages instead
// of re-declaring a shape by hand - if the backend model changes, the type
// changes here and every consumer fails to typecheck instead of drifting
// silently. Regenerate the underlying types with `npm run gen:types`.
import type { components } from "./api-types";

type Schemas = components["schemas"];

export type ConversationSummary = Schemas["ConversationSummary"];
export type ConversationDetail = Schemas["ConversationDetail"];
export type MessageDetail = Schemas["MessageDetail"];
export type ToolCallDetail = Schemas["ToolCallDetail"];
export type DocumentResponse = Schemas["DocumentResponse"];
export type PublicMessage = Schemas["PublicMessage"];
export type TenantResolveResponse = Schemas["TenantResolveResponse"];
export type CostDashboard = Schemas["CostDashboard"];
export type EvalDashboard = Schemas["EvalDashboard"];
export type EscalationResponse = Schemas["EscalationResponse"];
export type PricingRuleResponse = Schemas["PricingRuleResponse"];
export type PlatformMetrics = Schemas["PlatformMetrics"];
export type TenantSummary = Schemas["TenantSummary"];
export type BookingPage = Schemas["BookingPageResponse"];
// The editable profile slice and the PATCH body for it - shared by the
// business details screen and both of its edit sheets.
export type BusinessProfile = Schemas["BusinessProfile"];
export type ProfileUpdate = Schemas["ProfileUpdate"];
