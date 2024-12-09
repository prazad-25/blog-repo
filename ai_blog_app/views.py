from django.shortcuts import render,redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json,os
from pytube import YouTube
from django.conf import settings
import assemblyai as aai
import openai
from .models import BlogPost

@login_required
def index(request):
    return render(request,"index.html")

def user_login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request,username=username,password=password)
        if user is not None:
            login(request,user)
            return redirect('/')
        else:
            error_message = "Invalid username or password"
            return render(request,"login.html",{"error_message":error_message})

    return render(request,"login.html")


def user_logout(request):
    logout(request)
    return redirect('/')

def user_signup(request):
    if request.method=='POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatPassword = request.POST['repeatPassword']
        if password == repeatPassword:
            print(password,repeatPassword)
            try:
                user = User.objects.create_user(username,email,password)
                user.save()
                login(request,user)
                return redirect('/')
            except:
                error_message = "Error creating account"
                return render(request,"signup.html",{'error_message':error_message})
        else:
            error_message = 'Password incorrect'
            return render(request,"signup.html",{'error_message':error_message})
    return render(request,"signup.html")

@csrf_exempt
def generate_blog(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body) #dict value
            yt_link = data['link']
        except(KeyError,json.JSONDecodeError):
            return JsonResponse({'error':"Inavid data sent"},status=400)
        
        # get yt_title
        title = yt_title(yt_link)

        # get transcript
        transcription = get_transcription(yt_link)
        if not transcription :
            return JsonResponse({'error':"FAILED TO GET TRANSCRIPT"},status=500)

        # use openai to generate blog 
        blog_content = generate_blog_from_transcription(transcription)
        if not blog_content:
            return JsonResponse({'error':"FAILED TO GENERATE BLOG ARTICLE"},status=500)

        # save blog article
        new_blog_article = BlogPost.objects.create(
            user = request.user,
            youtube_title = title,
            youtube_link = yt_link,
            generated_content = blog_content,
        )
        new_blog_article.save()

        # return the article as a response
        return JsonResponse({"content":blog_content})
            


    else:
        return JsonResponse({'error':"Inavid request method"},status=405)
    
"""def yt_title(link):
    yt = YouTube(link)
    title = yt.title
    return title"""
from yt_dlp import YoutubeDL

def yt_title(link):
    try:
        # Use yt-dlp to extract video info
        with YoutubeDL() as ydl:
            info = ydl.extract_info(link, download=False)  # Don't download, just fetch metadata
        # Get the title from the extracted info
        title = info.get('title', 'Unknown Title')
        return title
    except Exception as e:
        return f"Error fetching title: {e}"
def get_transcription(link):
    audio_file = download_audio(link)
    aai.settings.api_key = "c776b90997d0461e9d8ebdbc429be710"
    
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file)
    
    return transcript.text

'''def download_audio(link):
    yt = YouTube(link)
    video = yt.streams.filter(only_audio=True).first()
    out_file = video.download(output_path=settings.MEDIA_ROOT)
    base,ext = os.path.splitext(out_file)
    new_file = base + '.mp3'
    os.rename(out_file,new_file)
    return new_file'''

def download_audio(link):
    output_dir = settings.MEDIA_ROOT  # Ensure MEDIA_ROOT is properly set in your settings
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
            audio_file = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            return audio_file
    except Exception as e:
        raise Exception(f"Failed to download audio: {e}")
import requests
def generate_blog_from_transcription(transcription):
    # Ensure the API key is set correctly
    api_key = "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"  # Replace with your API key
    
    # Define the URL for the model
    url = "https://api-inference.huggingface.co/models/gpt2"  # Public GPT-2 model for testing
    
    # Ensure the input doesn't exceed the token limit (1024 tokens)
    # Truncate the transcription to a smaller size if necessary
    max_input_tokens = 1024 - 100  # Reserve some tokens for the output, adjust as needed
    truncated_transcription = transcription[:max_input_tokens]
    
    # Define headers for authentication
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Define data for the POST request
    data = {
        "inputs": truncated_transcription,
        "max_new_tokens": 500,  # Limit the output to prevent exceeding total token limit
    }

    try:
        # Make the POST request to the Hugging Face API
        response = requests.post(url, headers=headers, json=data)

        # Check for a successful response
        if response.status_code == 200:
            response_data = response.json()
            
            # The response is a list, so extract the first item from the list
            if isinstance(response_data, list):
                generated_content = response_data[0].get("generated_text", "").strip()
                return generated_content
            else:
                raise Exception("Unexpected response format: Expected a list of results.")
        else:
            # Handle errors, such as token validation issues
            raise Exception(f"Failed to generate blog: {response.status_code} - {response.text}")

    except requests.exceptions.RequestException as e:
        # Handle network or request errors
        raise Exception(f"Request failed: {e}")

def blog_list(request):
    blog_article = BlogPost.objects.filter(user=request.user)
    return render(request,"all-blogs.html",{'blog_articles':blog_article})

def blog_details(request,pk):
    blog_article_details = BlogPost.objects.get(id=pk)
    if request.user == blog_article_details.user:
        return render(request,"blog-details.html",{'blog_article_detail':blog_article_details})
    else:
        return redirect('/')