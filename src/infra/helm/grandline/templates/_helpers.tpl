{{/* Common naming + labels for the GrandLine chart. */}}

{{- define "grandline.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "grandline.fullname" -}}
{{- printf "%s" (include "grandline.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "grandline.labels" -}}
app.kubernetes.io/name: {{ include "grandline.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
grandline.io/environment: {{ .Values.global.environment }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Per-component selector labels. Call with (dict "ctx" . "component" "backend"). */}}
{{- define "grandline.selectorLabels" -}}
app.kubernetes.io/name: {{ include "grandline.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "grandline.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (printf "%s-sa" (include "grandline.fullname" .)) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Fully-qualified image ref. Call with (dict "ctx" . "repo" "x" "tag" "y"). */}}
{{- define "grandline.image" -}}
{{- printf "%s/%s:%s" .ctx.Values.global.imageRegistry .repo .tag -}}
{{- end -}}
