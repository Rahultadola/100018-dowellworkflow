from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic.edit import CreateView
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
import json
from .models import SigningStep, WorkFlowModel, DocumentType, Document
from .forms import DocumentForm
from django.contrib.auth.models import User


# Create your views here.

def create_document_type(request, *args, **kwargs):
	try:
		body = json.loads(request.body)
	except:
		body = None

	if not body or not body['title'] :
		context = {
			'object': 'Error: Title required.'
		}
		return JsonResponse(context)


	internalWF = None
	externalWF = None

	if len(body['internal']) :
		internalWF = WorkFlowModel(title='internal')
		internalWF.save()
		for step in body['internal']:
			s = SigningStep(name=step['name'], authority= get_object_or_404(User, username=step['authority']))
			s.save()
			internalWF.steps.add(s)
		

	if len(body['external']) :
		externalWF = WorkFlowModel(title='external')
		externalWF.save()
		for step in body['external']:
			s = SigningStep(name=step['name'], authority= get_object_or_404(User, username=step['authority']))
			s.save()
			externalWF.steps.add(s)
		

	
	obj = DocumentType(title=body['title'], internal_work_flow=internalWF, external_work_flow=externalWF )
	obj.save()

	return JsonResponse({'id': obj.id, 'title': obj.title })


def getDocumentTypeObject(request, *args, **kwargs):
	obj = get_object_or_404(DocumentType, id=kwargs['id'])
	return JsonResponse({
			'id': obj.id,
			'title': obj.title,
			'internal_work_flow': {
				'title': obj.internal_work_flow.title ,
				'steps': [{ 'name': step.name, 'authority':step.authority.username} for step in obj.internal_work_flow.steps.all()],

			},
			'external_work_flow': {
				'title': obj.external_work_flow.title ,
				'steps': [{ 'name': step.name, 'authority':step.authority.username} for step in obj.external_work_flow.steps.all()],
			}
		}
	)



class DocumentWorkFlowAddView(View):
	form = DocumentForm()

	def get(self, request):
		user_list = User.objects.all()
		context = {
			'form': self.form,
			'user_list': user_list,
			'workflow': ['internal', 'external'] 
		}
		return render(request, 'workflow/add_document.html', context=context)

	def post(self, request):
		doc = Document(document_name=request.POST['document_name'], document_type=get_object_or_404(DocumentType, id=request.POST['document_type']), notify_users = True)

		if doc.document_type.internal_work_flow :
			doc.internal_wf_step = doc.document_type.internal_work_flow.steps.all()[doc.internal_status].name
		else:
			doc.internal_wf_step = None
			if doc.document_type.external_work_flow :
				doc.external_wf_step = doc.document_type.external_work_flow.steps.all()[doc.external_status].name
				
			else :
				doc.external_wf_step = None

		
		doc.save()
		messages.success(request, doc.document_name + ' - Added In WorkFlow - '+ doc.document_type.title)
		return redirect('workflow:documents-in-workflow')


class DocumentExecutionListView(ListView):
	model = Document

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		
		doc_list = []
		for document in context['document_list']:
			if document.document_type.internal_work_flow and (document.internal_wf_step != 'complete'):
				for step in document.document_type.internal_work_flow.steps.all():
					if (step.name == document.internal_wf_step) and (step.authority == self.request.user):
						doc_list.append(document)

			elif document.document_type.external_work_flow and (document.external_wf_step != 'complete'):
				for step in document.document_type.external_work_flow.steps.all():
					if step.name == document.external_wf_step and step.authority == self.request.user :
						doc_list.append(document)


		context['object_list'] = doc_list
		context['document_list'] = doc_list

		return context


def execute_wf(request, document_name, status, wf):
	authority = wf.steps.all()[status].authority
	step_name = None
	if request.user == authority :
		status += 1
		if status == len(wf.steps.all()) :
			step_name = 'complete'
			messages.success(request, document_name.title() + ' document Signed at all stages.')
			
		else:
			step_name = wf.steps.all()[status].name
			messages.info(request, document_name.title() + ' document Signed at :'+ wf.steps.all()[status - 1].name + '.')
	else:
		messages.error(request, 'You are NOT authorised')
		
	return status, step_name



class DocumentVerificationView(View):
	def get(self, request, **kwargs):
		id_ = kwargs.get('id')
		obj = get_object_or_404(Document, id=id_)
		return render(request, 'workflow/document_verify.html', { 'object': obj })

	def post(self, request, **kwargs):
		msg = None
		status = None
		step_name = None
		doc = get_object_or_404(Document, id=request.POST['id_'])

		if doc.document_type.internal_work_flow is not None and doc.internal_status < len(doc.document_type.internal_work_flow.steps.all()):
			status, step_name = execute_wf(request, doc.document_name, doc.internal_status, doc.document_type.internal_work_flow)
			if status and status != doc.internal_status :
				doc.internal_status = status
				doc.internal_wf_step = step_name

				if doc.internal_wf_step == 'complete':
					doc.external_wf_step = doc.document_type.external_work_flow.steps.all()[0].name

		elif doc.document_type.external_work_flow is not None and doc.external_status < len(doc.document_type.external_work_flow.steps.all()):
			status, step_name = execute_wf(request, doc.document_name, doc.external_status, doc.document_type.external_work_flow)
			if status and status != doc.external_status :
				doc.external_status = status
				doc.external_wf_step = step_name

		elif doc.external_wf_step == 'complete' :
			message.info(request, 'Document completed External WorkFlow.')
		else:
			messages.error(request, 'No WorkFlow Available')

		doc.save()
		return redirect('workflow:documents-in-workflow')


