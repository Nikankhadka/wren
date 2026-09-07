// AUTO-GENERATED from the backend OpenAPI schema by scripts/gen-api-types.mjs.
// Do not edit by hand; run `npm run gen:types` to refresh.

export interface paths {
    "/api/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Signup */
        post: operations["signup_api_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tenants/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_tenants_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/platform/ping": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ping */
        get: operations["ping_api_platform_ping_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/platform/metrics": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Metrics */
        get: operations["get_metrics_api_platform_metrics_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/platform/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tenants */
        get: operations["list_tenants_api_platform_tenants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/platform/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant Status */
        patch: operations["update_tenant_status_api_platform_tenants__tenant_id__patch"];
        trace?: never;
    };
    "/api/public/tenant/{slug}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Resolve Tenant */
        get: operations["resolve_tenant_api_public_tenant__slug__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/public/tenant/{slug}/storefront": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Storefront */
        get: operations["storefront_api_public_tenant__slug__storefront_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/public/tenant/{slug}/cover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Cover */
        get: operations["cover_api_public_tenant__slug__cover_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/onboarding/state": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get State */
        get: operations["get_state_api_onboarding_state_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/onboarding/knowledge/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Save Onboarding Knowledge */
        put: operations["save_onboarding_knowledge_api_onboarding_knowledge__document_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/onboarding/message": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Message */
        post: operations["post_message_api_onboarding_message_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/onboarding/message/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Message Stream */
        post: operations["post_message_stream_api_onboarding_message_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/onboarding/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm */
        post: operations["confirm_api_onboarding_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Documents */
        get: operations["list_documents_api_knowledge_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Document */
        post: operations["upload_document_api_knowledge_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/{document_id}/reprocess": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reprocess Document */
        post: operations["reprocess_document_api_knowledge__document_id__reprocess_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/urls": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ingest Url */
        post: operations["ingest_url_api_knowledge_urls_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/records": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Records
         * @description Everything the assistant knows, as readable sections.
         */
        get: operations["list_records_api_knowledge_records_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/drafts/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Draft From Upload
         * @description Read a file and return it as sections to review. Nothing is embedded yet -
         *     a draft answers no customer question until it is saved.
         */
        post: operations["draft_from_upload_api_knowledge_drafts_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/drafts/url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Draft From Url
         * @description Read a page and return it as sections to review (see /drafts/upload).
         */
        post: operations["draft_from_url_api_knowledge_drafts_url_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/records/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Record */
        get: operations["get_record_api_knowledge_records__document_id__get"];
        /**
         * Save Record
         * @description Save the owner's reviewed sections and make them answerable.
         */
        put: operations["save_record_api_knowledge_records__document_id__put"];
        post?: never;
        /** Delete Record */
        delete: operations["delete_record_api_knowledge_records__document_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/knowledge/records/{document_id}/source": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Source Detail */
        get: operations["get_source_detail_api_knowledge_records__document_id__source_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/page": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Booking Page */
        get: operations["get_booking_page_api_business_page_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/links": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Links */
        patch: operations["patch_links_api_business_links_patch"];
        trace?: never;
    };
    "/api/business/offerings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Offerings */
        get: operations["list_offerings_api_business_offerings_get"];
        put?: never;
        /** Post Offering */
        post: operations["post_offering_api_business_offerings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/offerings/{offering_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Offering */
        delete: operations["remove_offering_api_business_offerings__offering_id__delete"];
        options?: never;
        head?: never;
        /** Patch Offering */
        patch: operations["patch_offering_api_business_offerings__offering_id__patch"];
        trace?: never;
    };
    "/api/business/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Profile */
        get: operations["get_profile_api_business_profile_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Profile */
        patch: operations["patch_profile_api_business_profile_patch"];
        trace?: never;
    };
    "/api/business/cover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Cover */
        get: operations["get_cover_api_business_cover_get"];
        /** Put Cover */
        put: operations["put_cover_api_business_cover_put"];
        post?: never;
        /** Delete Cover */
        delete: operations["delete_cover_api_business_cover_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/offerings/{offering_id}/media/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upload Offering Media */
        put: operations["upload_offering_media_api_business_offerings__offering_id__media_upload_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/offerings/{offering_id}/media/url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Offering Media Url */
        put: operations["set_offering_media_url_api_business_offerings__offering_id__media_url_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/business/offerings/{offering_id}/media": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Offering Media */
        delete: operations["remove_offering_media_api_business_offerings__offering_id__media_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Chat */
        post: operations["chat_api_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Conversation Messages
         * @description T-031: unauthenticated transcript poll for the customer surface - the
         *     only way a resolved escalation's human_agent reply reaches an
         *     already-open customer tab (no push/websocket mechanism exists anywhere
         *     in this codebase). Trust model matches POST /api/chat's conversation_id:
         *     knowing the UUID is the capability, same as the rest of this bare
         *     customer surface (no login).
         *
         *     ``after`` lets a client that already has the transcript up to some
         *     timestamp poll for only what's new, rather than re-fetching the whole
         *     history on every 5s tick.
         */
        get: operations["get_conversation_messages_api_chat__conversation_id__messages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Conversations */
        get: operations["list_conversations_api_conversations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Conversation */
        get: operations["get_conversation_api_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/conversations/{conversation_id}/takeover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Take Over Conversation
         * @description C-6: the staff member is the voice now; the assistant stays silent until
         *     handed back. Available on any conversation, not only a flagged one - a
         *     business steps into its own conversations whenever it wants to.
         */
        post: operations["take_over_conversation_api_conversations__conversation_id__takeover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/conversations/{conversation_id}/handback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Hand Back Conversation
         * @description C-6: the assistant resumes. The takeover interlude stays in the history,
         *     so its next turn reads what the human said rather than contradicting it.
         */
        post: operations["hand_back_conversation_api_conversations__conversation_id__handback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/conversations/{conversation_id}/reply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reply As Human
         * @description C-6: a staff member's own words into the customer's open chat, picked up
         *     by the transcript poll C-5 left running.
         *
         *     Requires the conversation to be taken over first: replying underneath a
         *     live assistant would put two voices in one thread, each unaware of the
         *     other mid-turn.
         */
        post: operations["reply_as_human_api_conversations__conversation_id__reply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/escalations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Escalations */
        get: operations["list_escalations_api_escalations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/escalations/{escalation_id}/claim": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Claim Escalation */
        post: operations["claim_escalation_api_escalations__escalation_id__claim_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/escalations/{escalation_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve Escalation */
        post: operations["resolve_escalation_api_escalations__escalation_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pricing/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pricing Rules */
        get: operations["list_pricing_rules_api_pricing_rules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/pricing/rules/{rule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Pricing Rule */
        patch: operations["update_pricing_rule_api_pricing_rules__rule_id__patch"];
        trace?: never;
    };
    "/api/pricing/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Catalog Items */
        get: operations["list_catalog_items_api_pricing_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboards/costs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Cost Dashboard */
        get: operations["get_cost_dashboard_api_dashboards_costs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboards/evals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Eval Dashboard */
        get: operations["get_eval_dashboard_api_dashboards_evals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Readiness probe (the ALB target-group health check). Pings the DB so an
         *     instance that can't reach Postgres is pulled from rotation instead of
         *     serving 500s.
         */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Body_draft_from_upload_api_knowledge_drafts_upload_post */
        Body_draft_from_upload_api_knowledge_drafts_upload_post: {
            /** File */
            file: string;
        };
        /** Body_put_cover_api_business_cover_put */
        Body_put_cover_api_business_cover_put: {
            /** File */
            file: string;
        };
        /** Body_upload_document_api_knowledge_upload_post */
        Body_upload_document_api_knowledge_upload_post: {
            /** File */
            file: string;
            /** Doc Type */
            doc_type: string;
        };
        /** Body_upload_offering_media_api_business_offerings__offering_id__media_upload_put */
        Body_upload_offering_media_api_business_offerings__offering_id__media_upload_put: {
            /** File */
            file: string;
        };
        /** BookingPageOffering */
        BookingPageOffering: {
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Price Cents */
            price_cents: number | null;
            /** Category */
            category?: string | null;
            media?: components["schemas"]["OfferingMedia"] | null;
        };
        /** BookingPageResponse */
        BookingPageResponse: {
            /** Slug */
            slug: string;
            /** Name */
            name: string;
            /** Tagline */
            tagline: string | null;
            /** Links */
            links: {
                [key: string]: string;
            };
            /** Has Cover */
            has_cover: boolean;
            /** Cover Url */
            cover_url?: string | null;
            /** Offerings */
            offerings: components["schemas"]["BookingPageOffering"][];
        };
        /**
         * BudgetUsage
         * @description Where this month's spend sits against the standing testing budget (P-1).
         *     ``fraction`` is None when no budget is configured.
         */
        BudgetUsage: {
            /** Fraction */
            fraction: number | null;
            /** Warning */
            warning: boolean;
        };
        /**
         * BusinessProfile
         * @description The editable profile, every field present.
         *
         *     The response the console reads and the type the frontend generates from, so
         *     each field is a plain string rather than an optional: a value that was never
         *     captured is the empty string, which is what the screens already render.
         */
        BusinessProfile: {
            /** Abn */
            abn: string;
            /** Gst */
            gst: string;
            /** Customer Voice Preset */
            customer_voice_preset: string;
            /** Customer Voice Custom Style */
            customer_voice_custom_style: string;
        };
        /** CatalogItemResponse */
        CatalogItemResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Price Cents */
            price_cents: number | null;
            /** Active */
            active: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ChatRequest */
        ChatRequest: {
            /** Slug */
            slug: string;
            /** Conversation Id */
            conversation_id?: string | null;
            /** Message */
            message: string;
        };
        /** ChipSpec */
        ChipSpec: {
            /** Label */
            label: string;
            /** Value */
            value: string;
            /**
             * Dashed
             * @default false
             */
            dashed: boolean;
            /** Widget */
            widget?: ("text" | "chips" | "masked" | "cta" | "phone") | null;
        };
        /** ConversationDetail */
        ConversationDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Customer Ref */
            customer_ref: string | null;
            /** Channel */
            channel: string;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Total Cost Usd */
            total_cost_usd: number;
            /** Messages */
            messages: components["schemas"]["MessageDetail"][];
        };
        /** ConversationSummary */
        ConversationSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Customer Ref */
            customer_ref: string | null;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Message Count */
            message_count: number;
            /**
             * Needs Attention
             * @default false
             */
            needs_attention: boolean;
            /** Pending Summary */
            pending_summary?: string | null;
            /** Pending Since */
            pending_since?: string | null;
            /** Last Message */
            last_message?: string | null;
            /** Last Activity At */
            last_activity_at?: string | null;
        };
        /** CostDashboard */
        CostDashboard: {
            /** Cost Today Usd */
            cost_today_usd: number;
            /** Cost Yesterday Usd */
            cost_yesterday_usd: number;
            /** Cost This Month Usd */
            cost_this_month_usd: number;
            /** Cost Prev Month Usd */
            cost_prev_month_usd: number;
            /** Avg Cost Per Conversation Usd */
            avg_cost_per_conversation_usd: number | null;
            /** Conversation Count */
            conversation_count: number;
            /** Escalated Conversation Count */
            escalated_conversation_count: number;
            /** Escalation Rate */
            escalation_rate: number | null;
            /** Daily Costs */
            daily_costs: components["schemas"]["DailyCost"][];
            /** Monthly Budget Usd */
            monthly_budget_usd: number;
            monthly_budget_used: components["schemas"]["BudgetUsage"];
        };
        /** DailyCost */
        DailyCost: {
            /**
             * Day
             * Format: date
             */
            day: string;
            /** Cost Usd */
            cost_usd: number;
        };
        /** DocumentResponse */
        DocumentResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Filename */
            filename: string;
            /** Doc Type */
            doc_type: string;
            /** Status */
            status: string;
            /** Error */
            error: string | null;
        };
        /** EscalationResponse */
        EscalationResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Conversation Id
             * Format: uuid
             */
            conversation_id: string;
            /** Reason */
            reason: string;
            /** Summary */
            summary?: string | null;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Resolved At */
            resolved_at: string | null;
        };
        /** EvalCheck */
        EvalCheck: {
            /** Metric */
            metric: string;
            /** Value */
            value: number | null;
            /** Threshold */
            threshold: number;
            /** Passed */
            passed: boolean;
        };
        /** EvalDashboard */
        EvalDashboard: {
            /** Runs */
            runs: components["schemas"]["EvalRunSummary"][];
        };
        /** EvalRunSummary */
        EvalRunSummary: {
            /** Run Type */
            run_type: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Git Sha */
            git_sha: string;
            /** Metrics */
            metrics: {
                [key: string]: unknown;
            };
            /** Checks */
            checks: components["schemas"]["EvalCheck"][];
            /** Passed */
            passed: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /** HumanReplyRequest */
        HumanReplyRequest: {
            /** Message */
            message: string;
        };
        /** InputSpec */
        InputSpec: {
            /**
             * Kind
             * @default text
             * @enum {string}
             */
            kind: "text" | "chips" | "masked" | "cta" | "phone";
            /**
             * Placeholder
             * @default
             */
            placeholder: string;
            /** Chips */
            chips?: components["schemas"]["ChipSpec"][];
            /** Mask */
            mask?: string | null;
            /** Cta Label */
            cta_label?: string | null;
            /** Prefix */
            prefix?: string | null;
            /**
             * Suggest Owner Email
             * @default false
             */
            suggest_owner_email: boolean;
        };
        /**
         * KnowledgeRecord
         * @description A document as the knowledge screen reads it - the row plus its sections.
         */
        KnowledgeRecord: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Filename */
            filename: string;
            /** Doc Type */
            doc_type: string;
            /** Status */
            status: string;
            /** Error */
            error: string | null;
            /** Sections */
            sections: components["schemas"]["KnowledgeSection"][];
            /**
             * Offering Candidates
             * @default []
             */
            offering_candidates: components["schemas"]["PendingOffering"][];
            /**
             * Extraction Status
             * @default pending
             * @enum {string}
             */
            extraction_status: "full" | "partial" | "failed" | "pending";
        };
        /**
         * KnowledgeSection
         * @description One readable group in an owner's reviewed document.
         *
         *     Old documents used arbitrary headings. Reading them through this model gives
         *     them the structured shape without an eager data migration; their next save
         *     writes the normalized form back to ``documents.structured``.
         */
        KnowledgeSection: {
            /** Heading */
            heading: string;
            /** Body */
            body: string;
            /** Kind */
            kind?: ("business_overview" | "hours" | "location" | "other") | null;
        };
        /**
         * LinksUpdate
         * @description The four link slots. An empty string clears one; an absent key leaves it.
         */
        LinksUpdate: {
            /** Links */
            links?: {
                [key: string]: string;
            };
        };
        /** MessageDetail */
        MessageDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Role */
            role: string;
            /** Content */
            content: string;
            /** Agent Node */
            agent_node: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Metadata */
            metadata: {
                [key: string]: unknown;
            };
            /** Cost Usd */
            cost_usd: number | null;
            /** Tool Calls */
            tool_calls: components["schemas"]["ToolCallDetail"][];
        };
        /** OfferingCreate */
        OfferingCreate: {
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Price Dollars */
            price_dollars?: number | string | null;
            /** Category */
            category?: string | null;
        };
        /** OfferingMedia */
        OfferingMedia: {
            /**
             * Type
             * @enum {string}
             */
            type: "image" | "video";
            /**
             * Provider
             * @enum {string}
             */
            provider: "cloudinary" | "youtube" | "vimeo";
            /** Url */
            url: string;
            /** Poster Url */
            poster_url?: string | null;
        };
        /** OfferingMediaUrl */
        OfferingMediaUrl: {
            /** Url */
            url: string;
        };
        /** OfferingResponse */
        OfferingResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Price Cents */
            price_cents: number | null;
            /** Category */
            category?: string | null;
            media?: components["schemas"]["OfferingMedia"] | null;
        };
        /**
         * OfferingUpdate
         * @description A partial edit: an absent key means "leave this alone".
         *
         *     Only ``price_dollars`` reads an explicit null as a value - it clears the
         *     published price. ``name`` and ``description`` are ``not null`` columns, so
         *     a null for either is a 422 here rather than a constraint violation at the
         *     UPDATE; absence, not null, is how a field is left unchanged.
         */
        OfferingUpdate: {
            /** Name */
            name?: string | null;
            /** Description */
            description?: string | null;
            /** Price Dollars */
            price_dollars?: number | string | null;
            /** Category */
            category?: string | null;
        };
        /** OnboardingConfirmRequest */
        OnboardingConfirmRequest: {
            /** Slug */
            slug?: string | null;
        };
        /** OnboardingConfirmResponse */
        OnboardingConfirmResponse: {
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Slug */
            slug: string;
        };
        /** OnboardingKnowledgeRequest */
        OnboardingKnowledgeRequest: {
            /** Sections */
            sections?: components["schemas"]["KnowledgeSection"][];
            /** Offerings */
            offerings?: components["schemas"]["PendingOffering"][];
        };
        /** OnboardingKnowledgeResponse */
        OnboardingKnowledgeResponse: {
            record: components["schemas"]["KnowledgeRecord"];
            /** Offering Candidates */
            offering_candidates: components["schemas"]["PendingOffering"][];
        };
        /** OnboardingMessageRequest */
        OnboardingMessageRequest: {
            /** Text */
            text?: string | null;
            selection?: components["schemas"]["SelectionPayload"] | null;
            /**
             * Resume
             * @default false
             */
            resume: boolean;
        };
        /** OnboardingStateResponse */
        OnboardingStateResponse: {
            /** Stage */
            stage: string;
            /** Prompt */
            prompt: string;
            /** Draft */
            draft: {
                [key: string]: string;
            };
            /** Completed */
            completed: boolean;
            /** History */
            history: {
                [key: string]: string;
            }[];
            input: components["schemas"]["InputSpec"] | null;
            /** Can Confirm */
            can_confirm: boolean;
            /** Suggested Slug */
            suggested_slug: string | null;
            /** Offering Candidates */
            offering_candidates: components["schemas"]["PendingOffering"][];
            /** Paused Beat */
            paused_beat: string | null;
        };
        /**
         * PendingOffering
         * @description An offering waiting for owner review before it reaches the catalog.
         */
        PendingOffering: {
            /** Name */
            name: string;
            /**
             * Candidate Id
             * @default
             */
            candidate_id: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Price Cents */
            price_cents?: number | null;
            /** Sources */
            sources?: ("owner" | "document")[];
            /** Source References */
            source_references?: components["schemas"]["SourceReference"][];
            /**
             * Price Note
             * @default
             */
            price_note: string;
            /**
             * Needs Review
             * @default false
             */
            needs_review: boolean;
            /** Possible Matches */
            possible_matches?: string[];
            /** Price Options */
            price_options?: number[];
        };
        /** PlatformMetrics */
        PlatformMetrics: {
            /** Tenant Count */
            tenant_count: number;
            /** Total Cost Usd */
            total_cost_usd: number;
        };
        /** PricingRuleResponse */
        PricingRuleResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Code */
            code: string;
            /** Label */
            label: string;
            /** Unit Amount Cents */
            unit_amount_cents: number;
            /** Unit */
            unit: string;
            /** Active */
            active: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PricingRuleUpdate */
        PricingRuleUpdate: {
            /** Code */
            code?: string | null;
            /** Label */
            label?: string | null;
            /** Unit Amount Dollars */
            unit_amount_dollars?: number | string | null;
            /** Unit */
            unit?: string | null;
            /** Active */
            active?: boolean | null;
        };
        /**
         * ProfileUpdate
         * @description The ABN and its GST answer, and how the public assistant sounds - the
         *     slice of the profile that stays correctable after go-live.
         *
         *     Extra keys are refused rather than ignored: the rest of the profile is
         *     frozen at confirm, and a request that thought otherwise should hear so.
         */
        ProfileUpdate: {
            /** Abn */
            abn?: string | null;
            /** Gst */
            gst?: string | null;
            /** Customer Voice Preset */
            customer_voice_preset?: string | null;
            /** Customer Voice Custom Style */
            customer_voice_custom_style?: string | null;
        };
        /** PublicMessage */
        PublicMessage: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Role */
            role: string;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * PublicOffering
         * @description One offering as a customer sees it.
         *
         *     ``price_cents`` is the owner's own typed figure, passed through untouched -
         *     the page formats it, nothing computes it. Null means the owner published no
         *     price, and the page shows none rather than inventing one.
         */
        PublicOffering: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Price Cents */
            price_cents: number | null;
            /** Category */
            category?: string | null;
            media?: components["schemas"]["OfferingMedia"] | null;
        };
        /** ResolveRequest */
        ResolveRequest: {
            /** Message */
            message?: string | null;
        };
        /** SaveRecordRequest */
        SaveRecordRequest: {
            /**
             * Sections
             * @default []
             */
            sections: components["schemas"]["KnowledgeSection"][];
            /**
             * Offerings
             * @default []
             */
            offerings: components["schemas"]["PendingOffering"][];
            /**
             * Accept Price Changes
             * @default false
             */
            accept_price_changes: boolean;
        };
        /** SelectionPayload */
        SelectionPayload: {
            /** Beat */
            beat: string;
            /** Values */
            values?: string[];
        };
        /** SourceDetail */
        SourceDetail: {
            /** Text */
            text: string;
            /** Is Fallback */
            is_fallback: boolean;
        };
        /**
         * SourceReference
         * @description Verbatim evidence supporting a candidate field in its source.
         */
        SourceReference: {
            /** Block */
            block: string;
            /** Excerpt */
            excerpt: string;
            /** Supported Fields */
            supported_fields?: ("name" | "description" | "price")[];
        };
        /** StorefrontResponse */
        StorefrontResponse: {
            /** Name */
            name: string;
            /** Tagline */
            tagline: string | null;
            /** Links */
            links: {
                [key: string]: string;
            };
            /** Offerings */
            offerings: components["schemas"]["PublicOffering"][];
            /** Has Cover */
            has_cover: boolean;
            /** Cover Url */
            cover_url?: string | null;
        };
        /** TenantMeResponse */
        TenantMeResponse: {
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Slug */
            slug: string;
            /** Name */
            name: string;
            /** Brand */
            brand?: {
                [key: string]: unknown;
            };
        };
        /** TenantResolveResponse */
        TenantResolveResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Status */
            status: string;
            /** Brand */
            brand: {
                [key: string]: unknown;
            };
            /** Customer */
            customer: {
                [key: string]: unknown;
            };
        };
        /**
         * TenantSignupRequest
         * @description Both fields absent is the login-in-chat provisioning shape - see the
         *     module docstring and ``controller.signup``.
         */
        TenantSignupRequest: {
            /** Slug */
            slug?: string | null;
            /** Name */
            name?: string | null;
        };
        /** TenantSignupResponse */
        TenantSignupResponse: {
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Slug */
            slug: string;
        };
        /** TenantSummary */
        TenantSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Slug */
            slug: string;
            /** Name */
            name: string;
            /** Status */
            status: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Conversation Count */
            conversation_count: number;
            /** Cost Usd */
            cost_usd: number;
        };
        /** ToolCallDetail */
        ToolCallDetail: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Tool Name */
            tool_name: string;
            /** Arguments */
            arguments: {
                [key: string]: unknown;
            };
            /** Result */
            result: unknown;
            /** Success */
            success: boolean;
            /** Latency Ms */
            latency_ms: number | null;
        };
        /** UpdateTenantStatusRequest */
        UpdateTenantStatusRequest: {
            /** Status */
            status: string;
        };
        /** UrlIngestRequest */
        UrlIngestRequest: {
            /** Url */
            url: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** ProblemDetails */
        ProblemDetails: {
            /**
             * Type
             * @default about:blank
             */
            type: string;
            /** Title */
            title: string;
            /** Status */
            status: number;
            /** Detail */
            detail: string;
            /** Instance */
            instance: string;
            /** Code */
            code: string;
            /** Request Id */
            request_id: string;
            /**
             * Errors
             * @default null
             */
            errors: components["schemas"]["ProblemError"][] | null;
        };
        /** ProblemError */
        ProblemError: {
            /** Pointer */
            pointer: string;
            /** Code */
            code: string;
            /** Detail */
            detail: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    signup_api_tenants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantSignupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantSignupResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    me_api_tenants_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantMeResponse"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    ping_api_platform_ping_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_metrics_api_platform_metrics_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformMetrics"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_tenants_api_platform_tenants_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantSummary"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    update_tenant_status_api_platform_tenants__tenant_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateTenantStatusRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantSummary"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    resolve_tenant_api_public_tenant__slug__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantResolveResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    storefront_api_public_tenant__slug__storefront_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StorefrontResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    cover_api_public_tenant__slug__cover_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_state_api_onboarding_state_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OnboardingStateResponse"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    save_onboarding_knowledge_api_onboarding_knowledge__document_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OnboardingKnowledgeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OnboardingKnowledgeResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    post_message_api_onboarding_message_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OnboardingMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OnboardingStateResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    post_message_stream_api_onboarding_message_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OnboardingMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    confirm_api_onboarding_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["OnboardingConfirmRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OnboardingConfirmResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_documents_api_knowledge_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    upload_document_api_knowledge_upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document_api_knowledge_upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    reprocess_document_api_knowledge__document_id__reprocess_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    ingest_url_api_knowledge_urls_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UrlIngestRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_records_api_knowledge_records_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeRecord"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    draft_from_upload_api_knowledge_drafts_upload_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_draft_from_upload_api_knowledge_drafts_upload_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeRecord"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    draft_from_url_api_knowledge_drafts_url_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UrlIngestRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeRecord"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_record_api_knowledge_records__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeRecord"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    save_record_api_knowledge_records__document_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveRecordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeRecord"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    delete_record_api_knowledge_records__document_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_source_detail_api_knowledge_records__document_id__source_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceDetail"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_booking_page_api_business_page_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookingPageResponse"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    patch_links_api_business_links_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LinksUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_offerings_api_business_offerings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferingResponse"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    post_offering_api_business_offerings_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferingResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    remove_offering_api_business_offerings__offering_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                offering_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    patch_offering_api_business_offerings__offering_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                offering_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferingUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferingResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_profile_api_business_profile_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessProfile"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    patch_profile_api_business_profile_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BusinessProfile"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_cover_api_business_cover_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    put_cover_api_business_cover_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_put_cover_api_business_cover_put"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    delete_cover_api_business_cover_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    upload_offering_media_api_business_offerings__offering_id__media_upload_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                offering_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_offering_media_api_business_offerings__offering_id__media_upload_put"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferingMedia"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    set_offering_media_url_api_business_offerings__offering_id__media_url_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                offering_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferingMediaUrl"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferingMedia"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    remove_offering_media_api_business_offerings__offering_id__media_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                offering_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    chat_api_chat_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_conversation_messages_api_chat__conversation_id__messages_get: {
        parameters: {
            query: {
                slug: string;
                after?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicMessage"][];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_conversations_api_conversations_get: {
        parameters: {
            query?: {
                status?: ("open" | "human" | "escalated" | "closed") | null;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationSummary"][];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_conversation_api_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetail"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    take_over_conversation_api_conversations__conversation_id__takeover_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    hand_back_conversation_api_conversations__conversation_id__handback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    reply_as_human_api_conversations__conversation_id__reply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HumanReplyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_escalations_api_escalations_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EscalationResponse"][];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    claim_escalation_api_escalations__escalation_id__claim_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                escalation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EscalationResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    resolve_escalation_api_escalations__escalation_id__resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                escalation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResolveRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EscalationResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_pricing_rules_api_pricing_rules_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PricingRuleResponse"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    update_pricing_rule_api_pricing_rules__rule_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PricingRuleUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PricingRuleResponse"];
                };
            };
            /** @description Validation failed */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    list_catalog_items_api_pricing_catalog_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogItemResponse"][];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_cost_dashboard_api_dashboards_costs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CostDashboard"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    get_eval_dashboard_api_dashboards_evals_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvalDashboard"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description Problem details error */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["ProblemDetails"];
                };
            };
        };
    };
}
