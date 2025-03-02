import os
import shutil
import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from app.facenet.facenet import detect_faces
from app.utils.classification import get_classes
from app.utils.wrappers import exception_handler_wrapper
from app.utils.generateThumbnails import (
    generate_thumbnails_for_folders,
    generate_thumbnails_for_existing_folders
)
from app.config.settings import THUMBNAIL_IMAGES_PATH
from app.database.images import (
    get_all_image_ids_from_db,
    get_path_from_id,
    insert_image_db,
    delete_image_db,
    get_objects_db,
    extract_metadata,
    get_all_image_paths
)
from app.database.folders import(
    insert_folder,delete_folder,
    get_all_folders,
    get_folder_id_from_path
)
router = APIRouter()


async def run_get_classes(img_path,folder_id=None):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, get_classes, img_path)
    insert_image_db(img_path, result, extract_metadata(img_path),folder_id)
    if result:
        classes = result.split(",")
        if "0" in classes and classes.count("0") < 8:
            detect_faces(img_path)



@router.get("/all-images")
def get_images():
    try:
        image_files = get_all_image_paths()

        return JSONResponse(
            status_code=200,
            content={
                "data": {
                    "image_files": image_files
                },
                "message": "Successfully retrieved all images",
                "success": True,
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "message": str(e),
            },
        )

async def process_images(tasks):
    await asyncio.gather(*tasks)

@router.delete("/multiple-images")
def delete_multiple_images(payload: dict):
    try:
        paths = payload["paths"]
        is_from_device = payload["isFromDevice"]
        if not isinstance(paths, list):
            return JSONResponse(
                status_code=400,
                content={
                    "status_code": 400,
                    "content": {
                        "success": False,
                        "error": "Invalid 'paths' format",
                        "message": "'paths' should be a list",
                    },
                },
            )


        deleted_paths = []
        for path in paths:
            if not os.path.isfile(path):
                return JSONResponse(
                    status_code=404,
                    content={
                        "status_code": 404,
                        "content": {
                            "success": False,
                            "error": "Image not found",
                            "message": f"Image file not found: {path}",
                        },
                    },
                )
            path = os.path.normpath(path)
            folder_path, filename = os.path.split(path)

            thumbnail_folder = os.path.abspath(os.path.join(THUMBNAIL_IMAGES_PATH, "PictoPy.thumbnails"))
            thumb_nail_image_path = os.path.join(thumbnail_folder, filename)

            print("File = ",filename)

            # Check and remove the original file
            if os.path.exists(path):
                try:
                    if is_from_device : 
                        os.remove(path)
                except PermissionError:
                    print(f"Permission denied for file '{path}'.")
                except Exception as e:
                    print(f"An error occurred: {e}")
            else:
                print(f"File '{path}' does not exist.")


            # Check and remove the thumbnail file
            if os.path.exists(thumb_nail_image_path):
                try:
                    os.remove(thumb_nail_image_path)
                    print("Successfully removed!")
                except PermissionError:
                    print(f"Permission denied for file '{thumb_nail_image_path}'.")
                except Exception as e:
                    print(f"An error occurred: {e}")
            else:
                print(f"File '{thumb_nail_image_path}' does not exist.")

            delete_image_db(path)
            deleted_paths.append(path)

        return JSONResponse(
            status_code=200,
            content={
                "data": "Images",
                "message": "Images deleted successfully",
                "success": True,
            },
        )

    except Exception as e:
        print(e)
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "content": {
                    "success": False,
                    "error": "Internal server error",
                    "message": str(e),
                },
            },
        )


@router.get("/all-image-objects")
def get_all_image_objects():
    try:
        folder_paths = get_all_folders()
        generate_thumbnails_for_existing_folders()
        image_ids = get_all_image_ids_from_db()
        data = {}
        for image_id in image_ids:
            image_path = get_path_from_id(image_id)
            classes = get_objects_db(image_path)
            data[image_path] = classes if classes else "None"
            # print(image_path)
        
        thubnail_image_path = os.path.abspath(os.path.join(THUMBNAIL_IMAGES_PATH,"PictoPy.thumbnails"))

        return JSONResponse(
            status_code=200,
            content={
                # "data": data,
                "data": {"images": data , "image_path": thubnail_image_path},
                "message": "Successfully retrieved all image objects",
                "success": True,
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "content": {
                    "success": False,
                    "error": "Internal server error",
                    "message": str(e),
                },
            },
        )


@router.get("/class-ids")
def get_class_ids(path: str = Query(...)):
    try:
        if not path:
            return JSONResponse(
                status_code=400,
                content={
                    "status_code": 400,
                    "content": {
                        "success": False,
                        "error": "Missing 'path' parameter",
                        "message": "Image path is required",
                    },
                },
            )

        class_ids = get_objects_db(path)
        if not class_ids:
            return JSONResponse(
                status_code=200,
                content={
                    "data": {"class_ids": "None"},
                    "message": "No class IDs found for the image",
                    "success": True,
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "data": class_ids,
                "message": "Successfully retrieved class IDs",
                "success": True,
            },
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "content": {
                    "success": False,
                    "error": "Internal server error",
                    "message": str(e),
                },
            },
        )


@router.post("/add-folder")
async def add_folder(payload: dict):
    try:
        if "folder_path" not in payload:
            return JSONResponse(
                status_code=400,
                content={
                    "status_code": 400,
                    "content": {
                        "success": False,
                        "error": "Missing 'folder_path' in payload",
                        "message": "Folder path is required",
                    },
                },
            )

        folder_path = payload["folder_path"]
        if not os.path.isdir(folder_path):
            return JSONResponse(
                status_code=400,
                content={
                    "status_code": 400,
                    "content": {
                        "success": False,
                        "error": "Invalid folder path",
                        "message": "The provided path is not a valid directory",
                    },
                },
            )
        if not os.access(folder_path, os.R_OK) or not os.access(folder_path, os.W_OK) or not os.access(folder_path, os.X_OK):
            return JSONResponse(
            status_code=403,
            content={
                "status_code": 403,
                "content": {
                "success": False,
                "error": "Permission denied",
                "message": "The app does not have read and write permissions for the specified folder",
                },
            },
            )


        folder_id = get_folder_id_from_path(folder_path)
        if folder_id is None : 
            folder_id = insert_folder(folder_path)
       
        image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".gif"]
        tasks = []

        for root, _, files in os.walk(folder_path):
            if "PictoPy.thumbnails" in root:
                continue
            for file in files:
                file_path = os.path.join(root, file)
                file_extension = os.path.splitext(file_path)[1].lower()
                if file_extension in image_extensions:
                    tasks.append(asyncio.create_task(run_get_classes(file_path, folder_id=folder_id)))

        if not tasks:
            return JSONResponse(
                status_code=200,
                content={
                    "data": 0,
                    "message": "No valid images found in the specified folder",
                    "success": True,
                },
            )

        await asyncio.create_task(process_images(tasks))

        return JSONResponse(
            status_code=200,
            content={
                "data": len(tasks),
                "message": f"Processing {len(tasks)} images from the folder in the background",
                "success": True,
            },
        )

    except Exception as e:
        print(e)
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "content": {
                    "success": False,
                    "error": "Internal server error",
                    "message": str(e),
                },
            },
        )


# generate 400px width or height thumbnails for all the images present the given folder using pillow library
@router.post("/generate-thumbnails")
@exception_handler_wrapper
def generate_thumbnails(payload: dict):
    if "folder_paths" not in payload or not isinstance(payload["folder_paths"], list):
        return JSONResponse(
            status_code=400,
            content={
                "status_code": 400,
                "content": {
                    "success": False,
                    "error": "Invalid or missing 'folder_paths' in payload",
                    "message": "'folder_paths' must be a list of folder paths",
                },
            },
        )

    folder_paths = payload["folder_paths"]
    failed_paths = generate_thumbnails_for_folders(folder_paths)

    thumbnail_image_path = os.path.abspath(os.path.join(THUMBNAIL_IMAGES_PATH,"PictoPy.thumbnails"))

    if failed_paths:
        return JSONResponse(
            status_code=207,  # Multi-Status (some succeeded, some failed)
            content={
                "status_code": 207,
                "content": {
                    "success": False,
                    "error": "Partial processing",
                    "message": "Some folders or files could not be processed",
                    "failed_paths": failed_paths,
                    "thumbnail_path" : thumbnail_image_path
                },
            },
        )

    return JSONResponse(
        status_code=201,
        content={
            "data": "",
            "message": "Thumbnails generated successfully for all valid folders",
            "success": True,
            "thumbnail_path" : thumbnail_image_path
        },
    )


@router.get("/get-thumbnail-path")
@exception_handler_wrapper
def get_thumbnail_path() :
    print("GET request Received!") 
    thumbnail_path = os.path.abspath(os.path.join(THUMBNAIL_IMAGES_PATH,"PictoPy.thumbnails"))
    return JSONResponse(
        status_code=200,    
        content = {
            "success" : True,
            "thumbnailPath": thumbnail_path,
        }
    )

# Delete all the thumbnails present in the given folder
@router.delete("/delete-thumbnails")
@exception_handler_wrapper
def delete_thumbnails(folder_path: str | None = None):
    if not folder_path:
        return JSONResponse(
            status_code=400,
            content={
                "status_code": 400,
                "content": {
                    "success": False,
                    "error": "Missing 'folder_path' parameter",
                    "message": "Folder path is required",
                },
            },
        )

    if not os.path.isdir(folder_path):
        return JSONResponse(
            status_code=400,
            content={
                "status_code": 400,
                "content": {
                    "success": False,
                    "error": "Invalid folder path",
                    "message": "The provided path is not a valid directory",
                },
            },
        )

    # List to store any errors encountered while deleting thumbnails
    failed_deletions = []

    # Walk through the folder path and find all `PictoPy.thumbnails` folders
    for root, dirs, _ in os.walk(folder_path):
        for dir_name in dirs:
            if dir_name == "PictoPy.thumbnails":
                thumbnail_folder = os.path.join(root, dir_name)
                try:
                    # Delete the thumbnail folder
                    shutil.rmtree(thumbnail_folder)
                    print(f"Deleted: {thumbnail_folder}")
                except Exception as e:
                    failed_deletions.append(
                        {
                            "folder": thumbnail_folder,
                            "error": str(e),
                        }
                    )

    if failed_deletions:
        return JSONResponse(
            status_code=500,
            content={
                "status_code": 500,
                "content": {
                    "success": False,
                    "error": "Some thumbnail folders could not be deleted",
                    "message": "See the `failed_deletions` field for details.",
                    "failed_deletions": failed_deletions,
                },
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status_code": 200,
            "content": {
                "success": True,
                "message": "All PictoPy.thumbnails folders have been successfully deleted.",
            },
        },
    )