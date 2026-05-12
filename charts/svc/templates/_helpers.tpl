{{/*
Expand the name of the chart.
*/}}
{{- define "svc.name" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart label.
*/}}
{{- define "svc.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "svc.labels" -}}
helm.sh/chart: {{ include "svc.chart" . }}
{{ include "svc.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
Project: colab
{{- end }}

{{/*
Selector labels — used by Service and PodDisruptionBudget.
*/}}
{{- define "svc.selectorLabels" -}}
app.kubernetes.io/name: {{ include "svc.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: {{ include "svc.name" . }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "svc.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "svc.name" . }}-sa
{{- end }}
{{- end }}

{{/*
External Secret name (k8s Secret produced by ESO).
*/}}
{{- define "svc.externalSecretName" -}}
{{- include "svc.name" . }}-env
{{- end }}
