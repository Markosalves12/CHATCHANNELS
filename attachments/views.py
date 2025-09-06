from django.http import JsonResponse
from attachments.models import Attachment
from django.views.decorators.http import require_POST
from django.shortcuts import redirect


@require_POST  # Restricts to POST only for security
def upload_attachment(request):
    if not request.user.is_authenticated:
        return redirect('login')

    attachment_ids = []
    try:
        files = request.FILES.getlist('files')  # Matches the FormData key 'files'
        if not files:
            return JsonResponse({'error': 'Nenhum arquivo enviado'}, status=400)

        for file in files:
            # Determine attachment type based on content_type
            content_type = file.content_type.lower()
            attachment_type = 'other'
            if 'image' in content_type:
                attachment_type = 'image'
            elif 'video' in content_type:
                attachment_type = 'video'
            elif 'audio' in content_type:
                attachment_type = 'audio'
            elif 'application/pdf' in content_type:
                attachment_type = 'pdf'

            # Create the attachment (message=None initially)
            attachment = Attachment.objects.create(
                file=file,
                original_filename=file.name,
                attachment_type=attachment_type,
                # Add other fields if needed, e.g., uploaded_by=request.user
            )
            attachment_ids.append(attachment.id)

        return JsonResponse({'attachment_ids': attachment_ids})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
