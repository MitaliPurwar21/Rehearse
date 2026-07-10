{{- define "rehearse.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "rehearse.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "rehearse.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}

{{- /* Build the DATABASE_URL: in-cluster Postgres when enabled, otherwise the value you pass in. */ -}}
{{- define "rehearse.databaseUrl" -}}
{{- if .Values.postgres.enabled -}}
postgresql://{{ .Values.postgres.user }}:{{ .Values.postgres.password }}@{{ include "rehearse.fullname" . }}-postgres:5432/{{ .Values.postgres.db }}
{{- else -}}
{{ .Values.secrets.databaseUrl }}
{{- end -}}
{{- end -}}
