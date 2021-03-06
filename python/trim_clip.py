import io
import json
import os
import librosa
import numpy as np
import tempfile
from pathlib import Path

import ibm_boto3
from ibm_botocore.client import Config

import ffmpeg


def main(args):

    cos = createCOSClient(args)

    if not cos:
        raise ValueError(f"could not create COS instance")

    src_bucket = args.get('src_bucket')
    dst_bucket = args.get('dst_bucket')
    offset = float(args.get('offset')) / 1000
    key = args.get('rendition_key')

    # Create a temp dir for our files to use
    with tempfile.TemporaryDirectory() as tmpdir:

        # download file to temp dir
        file_path = Path(tmpdir, key)
        choir_id, song_id, part_id = file_path.stem.split('+')
        new_path = file_path.with_name(f'output-{file_path.stem}.mkv')
        cos.download_file(src_bucket, key, str(file_path))

        if offset:
            stream = ffmpeg.input(str(file_path))
            audio = stream.filter_('atrim', start=offset).filter_('asetpts', 'PTS-STARTPTS')
            video = stream.trim(start=offset).setpts('PTS-STARTPTS')
            out = ffmpeg.output(audio, video, str(new_path))
            stdout, stderr = out.run()
        else:
            new_path = file_path

        cos.upload_file(str(new_path), dst_bucket, f'{file_path.stem}.mkv')

        args["src_bucket"] = src_bucket
        args["dst_bucket"] = dst_bucket
        args["bucket"] = dst_bucket
        args["src_key"] = key
        args["dst_key"] = f'{file_path.stem}.mkv'
        args["choir_key"] = choir_id
        args["song_id"] = song_id
        args["part_id"] = part_id

        return args


def createCOSClient(args):
    """
    Create a ibm_boto3.client using the connectivity information
    contained in args.

    :param args: action parameters
    :type args: dict
    :return: An ibm_boto3.client
    :rtype: ibm_boto3.client
    """

    # if a Cloud Object Storage endpoint parameter was specified
    # make sure the URL contains the https:// scheme or the COS
    # client cannot connect
    if args.get('endpoint') and not args['endpoint'].startswith('https://'):
        args['endpoint'] = 'https://{}'.format(args['endpoint'])

    # set the Cloud Object Storage endpoint
    endpoint = args.get('endpoint',
                        'https://s3.us.cloud-object-storage.appdomain.cloud')

    # extract Cloud Object Storage service credentials
    cos_creds = args.get('__bx_creds', {}).get('cloud-object-storage', {})

    # set Cloud Object Storage API key
    api_key_id = \
        args.get('apikey',
                 args.get('apiKeyId',
                          cos_creds.get('apikey',
                                        os.environ
                                        .get('__OW_IAM_NAMESPACE_API_KEY')
                                        or '')))

    if not api_key_id:
        # fatal error; it appears that no Cloud Object Storage instance
        # was bound to the action's package
        return None

    # set Cloud Object Storage instance id
    svc_instance_id = args.get('resource_instance_id',
                               args.get('serviceInstanceId',
                                        cos_creds.get('resource_instance_id',
                                                      '')))
    if not svc_instance_id:
        # fatal error; it appears that no Cloud Object Storage instance
        # was bound to the action's package
        return None

    ibm_auth_endpoint = args.get('ibmAuthEndpoint',
                                 'https://iam.cloud.ibm.com/identity/token')

    # Create a Cloud Object Storage client using the provided
    # connectivity information
    cos = ibm_boto3.client('s3',
                           ibm_api_key_id=api_key_id,
                           ibm_service_instance_id=svc_instance_id,
                           ibm_auth_endpoint=ibm_auth_endpoint,
                           config=Config(signature_version='oauth'),
                           endpoint_url=endpoint)

    # Return Cloud Object Storage client
    return cos
