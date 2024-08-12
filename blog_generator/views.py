from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import json
from pytube import YouTube
from pytube.exceptions import AgeRestrictedError
import yt_dlp
import os
import assemblyai as aai
import openai
import google.generativeai as genai
from .models import BlogPost


# Create your views here.
@login_required
def index(request):
    return render(request, 'index.html')

def yt_title(link):
    ydl_opts = {}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(link, download=False)
        title = info_dict.get('title', None)
    return title

def download_audio(link):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(settings.MEDIA_ROOT, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(link, download=True)
        audio_file = ydl.prepare_filename(info_dict)
        base, ext = os.path.splitext(audio_file)
        new_file = f"{base}.mp3"
        if os.path.exists(new_file):
            return new_file
        else:
            raise Exception("Failed to download the audio")

def get_transcription(link):
    audio_file = download_audio(link)
    aai.settings.api_key = "8bdabd8fce9740a697ff06d65b3f3d4d"
    
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file)
    
    return transcript.text

api_key = os.getenv("API_KEY")
genai.configure(api_key=api_key)

def generate_blog_from_transcription(transcription):
    
    prompt = f"Based on the transcript that follows extracted from a Youtube video, give me a comprehensive summary of the content of the video and write it like a blog article:\n\n{transcription}\n\nArticle:"

    # Make a request to the Google Generative AI API
    response = genai.generate_text(
        prompt=prompt,
        temperature=0.7,
        candidate_count=1
    )
    # Access the generated content
    if response.candidates:
        generated_content = response.candidates[0]['output'].strip()  # Use 'output' to access the content
    elif response.result:
        generated_content = response.result.strip()  # Fallback if 'candidates' is empty or not used
    else:
        generated_content = "No content generated."

    return generated_content
    
@csrf_exempt
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            yt_link = data['link']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data sent'}, status=400)
        
        #get the title of video
        title = yt_title(yt_link)
        
        #get transcript
        transcription = get_transcription(yt_link)
        if not transcription:
            return JsonResponse({'error': "Failed to get transcript"}, status=500)
        
        #OpenAI to generate blog
        blog_content = generate_blog_from_transcription(transcription)
        if not blog_content:
            return JsonResponse({'error': "Failed to generate article"}, status=500)
        
        #save blog to DB
        new_blog_article = BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content,
        )
        new_blog_article.save()
        
        #return blog as response
        
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def blog_list(request):
    blog_articles = BlogPost.objects.filter(user=request.user)
    return render(request, "all-blogs.html", {'blog_articles': blog_articles})

def blog_details(request, pk):
    blog_article_detail = BlogPost.objects.get(id=pk)
    if request.user == blog_article_detail.user:
        return render(request, 'blog-details.html', {'blog_article_detail': blog_article_detail})
    else:
        return redirect('/')

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            error_message = "Invalid Username or Password"
            return render(request, 'login.html', {'error_message':error_message})

    return render(request, 'login.html')

def user_signup(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatPassword = request.POST['repeatPassword']
        if password == repeatPassword:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except:
                error_message = 'Error creating account'
                return render(request, 'signup.html', {'error_message':error_message})
        else:
            error_message = 'Passwords do not match'
            return render(request, 'signup.html', {'error_message':error_message})
    return render(request, 'signup.html')

def user_logout(request):
    logout(request)
    return redirect('/')