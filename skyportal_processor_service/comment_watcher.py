import argparse
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import traceback
from typing import Dict, List, Optional, Set, Tuple
import json

import requests
from config import get_required_env, load_env_file
from requests.auth import HTTPBasicAuth
import logging
logging.getLogger().setLevel(logging.DEBUG)

# TODO
# Do we need to continue where left off based on comments? Maybe just start listening from now() and not care about past?
# stdweb stacking takes stdweb-relative paths from the config -> should be changed to relative to TASKS_PATH probably
# verify radec of Skyportal source is the one we need
# uploading files takes time -> maybe put into separate thread
# put group id everywhere
# docker-compose
# tests

header = {}
seen_comments: Dict[str, Set[str]] = dict()  # Track seen comments (by source + created at) to avoid duplication

jobformat_version = 0.1
@dataclass
class PipelineJob:
    """
    Data structure for saving the state of a pipeline job.
    """
    comment: str = ""
    source_id: str = ""
    job_id: int = 0  # Local for the source
    # Stages:
    #  see pipeline_tick
    #  1000 - done
    #  1001 - error
    stage: int = 0
    ra: float = 0
    dec: float = 0
    author: str = ""
    telescope: str = ""
    stdweb_id: int = -1
    do_stacking: bool = False
    version: float = jobformat_version

    # Dict is very inefficient, but back-compatible
    def serialize(self) -> str:
        return json.dumps({
            "comment": self.comment,
            "source_id": self.source_id,
            "job_id": self.job_id,
            "stage": self.stage,
            "ra": self.ra,
            "dec": self.dec,
            "author": self.author,
            "telescope": self.telescope,
            "stdweb_id": self.stdweb_id,
            "do_stacking": self.do_stacking,
            "version": self.version,
            })

    @staticmethod
    def deserialize(string: str) -> "PipelineJob":
        fields = json.loads(string)
        return PipelineJob(
            comment=fields["comment"],
            source_id=fields["source_id"],
            job_id=fields["job_id"],
            stage=fields["stage"],
            ra=fields.get("ra", 0),
            dec=fields.get("dec", 0),
            author=fields.get("author",""),
            telescope=fields.get("telescope", ""),
            stdweb_id=fields.get("stdweb_id", -1),
            do_stacking=fields.get("do_stacking", False),
            version=fields.get("version", 0.0),
        )
pipeline: List[PipelineJob] = []


def str_to_varsel_str(message: str) -> str:
    """
    Encode a string as a string of variation selectors (invisible unicode characters that take up 0 pixels).
    Each two characters in the output string are 4 bytes in total and they encode 1 byte of the input string.
    """
    return "".join(map(lambda x: chr(0xfe00+x%16)+chr(0xfe00+x//16), message.encode("utf-8")))


def varsel_str_to_str(invisible_chars: str) -> str:
    """
    Decode a string from a string of variation selectors (invisible unicode characters that take up 0 pixels).
    Each two characters in the input string are 4 bytes in total and they encode 1 byte of the output string. Therefore the length of the input must be even.
    """
    bytelist = []
    for i in range(0, len(invisible_chars), 2):
        bytelist.append(
            (ord(invisible_chars[i  ])-0xfe00) + 
            (ord(invisible_chars[i+1])-0xfe00) * 16
        )
    return bytes(bytelist).decode("utf-8")


def get_new_comments(
    start_time: datetime, last_iteration: Optional[datetime]
) -> Tuple[List[PipelineJob], datetime]:
    """
    Fetch new comments from SkyPortal with an optional tag filter and converts them from jobs. If this is the first run, this will restore jobs to the states they were in.

    Updates the last_iteration timestamp before making the API call to ensure
    no comments are missed between polling cycles. Only returns comments that
    haven't been seen before (tracked in the global seen_comments set).

    Args:
        start_time: Initial start time for fetching sources
        last_iteration: Timestamp of last successful fetch, or None for first run

    Returns:
        Tuple of (list of jobs, updated last iteration timestamp)
    """
    since = last_iteration if last_iteration else start_time

    # Update last iteration before fetching new sources to avoid missing any sources
    last_iteration = datetime.utcnow().replace(tzinfo=timezone.utc)

    response = requests.get(
        f"{INSTANCE_URL}/api/sources",
        params={
            "includeComments": True,
            "commentsFilter": [SKYPORTAL_COMMAND],
            "commentsFilterAfter": since.isoformat(),
            #"group_ids": SKYPORTAL_GROUP_IDS_FILTER,
        },
        headers=header,
    )
    response.raise_for_status()
    logger.debug(f"Respose time: {response.elapsed.total_seconds() * 1000}ms")

    sources = response.json()["data"]["sources"]
    new_jobs = {}
    for source in sources:
        comments = source["comments"]
        if source["id"] not in seen_comments:
            seen_comments[source["id"]] = set()
        seen_comments_for_source = seen_comments[source["id"]]

        for comment in comments:
            job_id = comment["id"]
            if comment["bot"]:
                if comment["text"][0] == "№":
                    # Pick up where we left off
                    job = job_from_comment(comment["text"])
                    if job and job.job_id:
                        # Skip if already in pipeline
                        skip = False
                        for job2 in pipeline:
                            if job2.job_id == job.job_id and job2.source_id == job.source_id:
                                skip = True
                        if not skip:
                            new_jobs[job.job_id] = job
                continue
            if SKYPORTAL_COMMAND not in comment["text"]:
                continue
            if comment["created_at"] in seen_comments_for_source:
                continue
            # Filter by created at, so that modifying the comment doesn't do anything
            seen_comments_for_source.add(comment["created_at"])
            # New comment with required command!
            new_jobs[job_id] = PipelineJob(
                comment=comment["text"],
                source_id=source["id"],
                job_id=job_id,
                stage=1,
                ra=source["ra"],
                dec=source["dec"],
                author=comment["author_id"],
            )
    to_process = list(filter(lambda j: j.stage < 1000, new_jobs.values()))
    return to_process, last_iteration


def comment_back(job: PipelineJob, message: str) -> None:
    """
    Post a comment to SkyPortal to report the progress of the job.
    """
    response = requests.post(
        f"{INSTANCE_URL}/api/sources/{job.source_id}/comments",
        json={
            "text": f"№{job.job_id}:{str_to_varsel_str(job.serialize())} {message} @{job.author}",
            #"group_ids": SKYPORTAL_GROUP_IDS_FILTER,
        },
        headers=header,
    )
    response.raise_for_status()


def job_from_comment(comment: str) -> Optional[PipelineJob]:
    """
    Parse the hidden serialized job from a bot comment, if any.
    """
    text1 = comment.split(":")
    if len(text1) < 2:
        return None
    text2 = text1[1].split(" ")[0]
    if not text2.strip():
        return None
    text = varsel_str_to_str(text2)
    try:
        return PipelineJob.deserialize(text)
    except Exception:
        traceback.print_exc()
        return None


def owncloud_exists(path: str) -> bool:
    """
    Check if a file or folder exists and is accessible in OwnCloud.
    """
    check_url = f"{BASE_URL}/remote.php/dav/files/{OWNCLOUD_USER_ID}/{SAVE_PATH}/{path}"
    response = requests.request(
        "PROPFIND", check_url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN), headers={"Depth":"0"}
    )
    return response.status_code in [200, 207]


def owncloud_ls(path: str, depth: int = 1) -> Tuple[List[str], List[str]]:
    """
    List all files and folders in an OwnCloud directory.

    Depth indicates whether to also list contents of subfolders: 1 is just the requested folder, 2 is including its subfolder, etc

    Returns a list of full paths and a list of relative paths
    """
    check_url = f"{BASE_URL}/remote.php/dav/files/{OWNCLOUD_USER_ID}/{SAVE_PATH}/{path}"
    response = requests.request(
        "PROPFIND", check_url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN), headers={"Depth":str(depth)}
    )

    if response.status_code != 207:
        return [], []
    
    result = []
    result_short = []
    i1 = response.text.find("<d:href>")
    while i1 != -1:
        i2 = response.text.find("</d:href>", i1)
        if i2 == -1:
            return result, result_short
        file = response.text[i1+len("<d:href>"):i2]
        result.append(file)
        result_short.append(file[len(check_url)-len(BASE_URL):])
        i1 = response.text.find("<d:href>", i2)
    return result, result_short


def stdweb_make_task(job: PipelineJob) -> int:
    """
    Create a new task for processing files and upload files to it.
    Returns task id of the new task.
    """
    response = requests.request(
        "POST", f"{STDWEB_URL}/api/tasks/", 
        headers={"Authorization": f"Token {STDWEB_TOKEN}"},
        data={
            "original_name": f"{job.source_id}/{job.telescope} : {job.job_id}"
        }
    )
    response.raise_for_status()
    return response.json()["id"]


def stdweb_start_task(job: PipelineJob, files: List[str]) -> None:
    """
    Set config of the task on StdWeb an start it.
    """
    steps = [
                "inspect", 
                "photometry", 
                # "simple_transients", 
                # "subtraction",
            ]
    if job.do_stacking:
        steps.insert(0, "stack")
    response = requests.request(
        "POST", f"{STDWEB_URL}/api/tasks/{job.stdweb_id}/process/",
        headers={"Authorization": f"Token {STDWEB_TOKEN}"},
        json={
            "steps": steps,
            "config": {
                "stack_filenames": files,
                "target": f"{job.ra:.15f},{job.dec:.15f}",
            }
        }
    )
    response.raise_for_status()


def stdweb_task_status(job: PipelineJob) -> str:
    """
    Queries StdWeb task status.
    Returns task status as string.
    """
    response = requests.request(
        "GET", f"{STDWEB_URL}/api/tasks/{job.stdweb_id}", 
        headers={"Authorization": f"Token {STDWEB_TOKEN}"}
    )
    response.raise_for_status()
    return response.json()["state"]

def transfer_file_owncloud_to_stdweb(owncloud_path: str, stdweb_task_id: int, stdweb_filename: Optional[str] = None) -> None:
    response = requests.request(
        "GET", BASE_URL+owncloud_path, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_TOKEN)
    )
    response.raise_for_status()
    if stdweb_filename is None:
        stdweb_filename = owncloud_path.split("/")[-1]
    response2 = requests.request(
        "POST", f"{STDWEB_URL}/api/tasks/{stdweb_task_id}/files/{stdweb_filename}",
        headers={"Authorization": f"Token {STDWEB_TOKEN}"},
        files={"file": (stdweb_filename, response.content, "application/fits")}
    )
    response2.raise_for_status()


def pipeline_tick(job: PipelineJob) -> bool:
    """
    Main function that runs for all jobs. Broken up into pieces to allow waiting for something to happen asynchronously (and continuing from checkpoints even after restarting python).

    Flow (labelled by job.stage):
    1. Parse the arguments and return error if necessary
    2. Check if the requested folder existst in OwnCloud and contains .fits files
    3. Create a new task on StdWeb
    4. Upload .fits files from OwnCloud to StdWeb
    5. Start the StdWeb task
    6. Wait until the task state has "failed" or is "photometry_done"
    1000. Done
    1001 = Error caught

    Returns whether the job has finished
    """
    try:
        if job.stage <= 1:  # Immediately after seeing the comment
            job.stage = 2
            command = job.comment.split(SKYPORTAL_COMMAND)[1]
            argv = command.split(" ")
            if argv[0]:
                help_message = f"Usage: {SKYPORTAL_COMMAND} <telescope>\nCreates a stacked task in StdWeb from the images in OwnCloud. When the task is done uploads the photometry to SkyPortal.\nAlso:\n{SKYPORTAL_COMMAND}help\n{SKYPORTAL_COMMAND}dump [limit]\n{SKYPORTAL_COMMAND}show <invisible text>."
                # This is a special command
                if argv[0] == "help":
                    job.stage = 1000
                    comment_back(job, help_message)
                    return True
                if argv[0] == "dump":
                    job.stage = 1000
                    count = len(pipeline)
                    if len(argv) > 1 and argv[1].isdigit():
                        count = min(len(pipeline), int(argv[1]))
                    comment_back(job, "\n"+"\n".join(map(lambda j: j.serialize(), pipeline[0:count])))
                    return True
                if argv[0] == "show":
                    job.stage = 1000
                    count = 100
                    if len(argv) > 1:
                        if argv[1].isdigit():
                            count = int(argv[1])
                        else:
                            decoded = varsel_str_to_str("".join(filter(lambda x: 0xfe00 <= ord(x) <= 0xfe0f, command)))
                            comment_back(job, decoded)
                            return True
                    comment_back(job, "TODO, for now you have to give №x: .")
                    return True
                job.stage = 1001
                comment_back(job, f"Unrecognized command. {help_message}")
                return True

            # This is a plain command, expect a telescope name next
            if len(argv) < 2:
                job.stage = 1001
                comment_back(job, "Error: Please provide the name of the instrument to stack.")
                return True
            job.telescope = argv[1]
            job.stage = 2
        folder = f"{job.source_id}/{job.telescope}"
        if job.stage <= 2:
            if not owncloud_exists(folder):
                job.stage = 1001
                comment_back(job, f"Error: folder {SAVE_PATH}/{folder} not found in OwnCloud.")
                return True
        # The file paths are needed for a couple of stages
        if job.stage <= 5:
            files, files_short = owncloud_ls(folder)
            fits_files = [f for f in files if f.endswith(".fits") or f.endswith(".fit")]
            job.do_stacking = len(fits_files) > 1
        if job.stage <= 2:
            if not fits_files:
                job.stage = 1001
                comment_back(job, f"Error: (TODO)folder {SAVE_PATH}/{folder} does not contain .fits files.\nI see:\n{"\n".join(files_short)}")
                return True
            job.stage = 3
            comment_back(job, f"{len(fits_files)} files found.")
        if job.stage <= 3:
            #TODO see if there is already a task in StdWeb with same files
            job.stdweb_id = stdweb_make_task(job)
            job.stage = 4
            comment_back(job, f"{STDWEB_URL}/tasks/{job.stdweb_id}")
        if job.stage <= 4:
            if job.do_stacking:
                for path in fits_files:
                    transfer_file_owncloud_to_stdweb(path, job.stdweb_id)
            else:
                # Already checked that there is at least one file in stage 2
                transfer_file_owncloud_to_stdweb(fits_files[0], job.stdweb_id, "image.fits")
            job.stage = 5
            comment_back(job, f"{len(fits_files)} files uploaded.")
        if job.stage <= 5:
            files_to_stack = list(map(lambda f: f"tasks/{job.stdweb_id}/{f.split("/")[-1]}", fits_files))
            stdweb_start_task(job, files_to_stack)
            job.stage = 6
            comment_back(job, "Task started.")
            return False
        # Wait for the task to finish
        if job.stage <= 6:
            status = stdweb_task_status(job)
            if "failed" in status:
                job.stage = 1001
                comment_back(job, f"Error: {STDWEB_URL}/tasks/{job.stdweb_id}")
                return True
            if status != "photometry_done":
                return False # Wait and query again
            job.stage = 7
            comment_back(job, "Stdweb done. Ready to upload photometry")
    except Exception as e:
        job.stage = 1001
        traceback.print_exc()
        logger.error(f"Error while processing job #{job.job_id} for source {job.source_id}")
        # Hopefully this will not error
        comment_back(job, str(e))
        return True
    if job.stage < 1000:
        job.stage = 1000
        comment_back(job, "Done")
    return True

def pipeline_tick_all() -> None:
    """
    Run all tasks in the pipeline and remove the ones that have finished.
    """
    i = 0
    while i < len(pipeline):
        job = pipeline[i]
        if pipeline_tick(job):
            pipeline.pop(i)
        else:
            i += 1

def main_loop(start_time: datetime) -> None:
    """
    Main monitoring loop that watches for new comments, creates and runs jobs.

    Continuously polls SkyPortal and runs active pipeline jobs.

    Args:
        start_time: Datetime to start monitoring from
    """
    # try:
    #     create_base_folder_on_owncloud()
    # except Exception as e:
    #     logger.error(f"Error during base folder creation: {e}")

    logger.info("Listening for new sources...\n")

    last_iteration = None
    while True:
        try:
            new_comments, last_iteration = get_new_comments(start_time, last_iteration)
            for job in new_comments:
                source_id = job.source_id
                logger.info(f"New command detected for {source_id}: {job.comment}")
                pipeline.append(job)
            if new_comments:
                logger.info("Listening for new comments...")
            
            pipeline_tick_all()
        except Exception as e:
            logger.error(f"Error: {e}")
        time.sleep(POLL_INTERVAL)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed command line arguments namespace
    """
    parser = argparse.ArgumentParser(
        description=(
            "SkyPortal source watcher\nAuto-create folders in ownCloud for new sources.\n\n"
            "Example:\n"
            "  python source_watcher.py --env-file .env.local\n"
            "  python source_watcher.py --start-time '2025-05-15T00:00:00Z'\n\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Path to .env configuration file (default: .env)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Parse arguments and load environment
    args = parse_args()
    load_env_file(args.env_file)

    # Setup logger
    # slack_token = os.getenv("SLACK_BOT_TOKEN")
    # service_name = os.getenv("SLACK_SERVICE_NAME", "owncloud-folder-service")
    # channel = "#" + service_name
    logger = logging #setup_logger(service_name, slack_token, channel)

    try:
        BASE_URL = os.getenv(
            "OWNCLOUD_BASE_URL",
            "https://grandma-owncloud.lal.in2p3.fr",
        )
        OWNCLOUD_USERNAME = get_required_env("OWNCLOUD_USERNAME")
        OWNCLOUD_TOKEN = get_required_env("OWNCLOUD_TOKEN")
        OWNCLOUD_USER_ID = get_required_env("OWNCLOUD_USER_ID")
        INSTANCE_URL = os.getenv(
            "SKYPORTAL_URL", "https://skyportal-icare.ijclab.in2p3.fr"
        )
        SKYPORTAL_TOKEN = get_required_env("SKYPORTAL_TOKEN")
        STDWEB_URL = os.getenv(
            "STDWEB_URL", "https://grandma-stdpipe.ijclab.in2p3.fr"
        )
        STDWEB_TOKEN = get_required_env("STDWEB_TOKEN")


        SAVE_PATH = os.getenv("SAVE_PATH", "Candidates/Skyportal")
        SOURCE_TAG = os.getenv("SOURCE_TAG", "")
        POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
        SKYPORTAL_GROUP_IDS_FILTER = [
            int(x.strip()) for x in os.getenv("GROUP_IDS", "").split(",") if x.strip()
        ]
        SKYPORTAL_COMMAND=os.getenv("SKYPORTAL_COMMAND", "@Process")

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error(
            "Required variables: OWNCLOUD_USERNAME, OWNCLOUD_TOKEN, OWNCLOUD_USER_ID, SKYPORTAL_TOKEN, STDWEB_TOKEN"
        )
        exit(1)
    header = {"Authorization": f"token {SKYPORTAL_TOKEN}"}

    # Parse start time from environment variable
    start_time_str = os.getenv("START_TIME")
    if start_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        except ValueError:
            logger.error(
                "Invalid START_TIME format. Use ISO format, e.g. '2025-10-20T00:00:00Z'"
            )
            exit(1)
    else:
        start_time = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=1)

    main_loop(start_time)
