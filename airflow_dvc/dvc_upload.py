"""
Abstraction for DVC upload sources.

@Piotr Styczyński 2021
"""
from abc import ABCMeta, abstractmethod
from typing import Callable
import inspect
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

try:
    from StringIO import StringIO ## for Python 2
except ImportError:
    from io import StringIO ## for Python 3


class DVCUpload(metaclass=ABCMeta):
    """
    Base class for all DVC uploads.
    The DVCUpload corresponds to an abstract request to upload a file to the upstream.
    """
    dvc_path: str # Path to he GIT repo that is an upstream target
    # Abstract resource that is created by __enter__ and destroyed with __exit__
    # All implementations of DVCUpload can freely choose what this resource is
    # It can be file-like object or other object containing state information
    _resource = None
    instance_context: str

    def __init__(self, dvc_path: str):
        self.dvc_path = dvc_path
        curframe = inspect.currentframe()
        caller = inspect.getouterframes(curframe, 2)[2]
        caller_path = caller.filename.split("/")[-1]
        self.instance_context = f"({caller_path}:{caller.lineno})"

    def __enter__(self):
        """
        Open resource for upload
        """
        if self._resource is None:
            self._resource = self.open()
        return self._resource

    def __exit__(self, type, value, traceback):
        """
        Close resource after upload
        """
        if self._resource is not None:
            self.close(self._resource)
        self._resource = None

    @abstractmethod
    def describe_source(self) -> str:
        """
        Human-readable message about the upload source
        """
        raise Exception("Operation is not supported: describe_source() invoked on abstract base class - DVCUpload")

    @abstractmethod
    def open(self):
        """
        Custom implementation of the upload behaviour.
        Method shouldn't be called directly, but rather invoked via context (__enter__).
        open() should return an object that has at least read() method.
        """
        raise Exception("Operation is not supported: open() invoked on abstract base class - DVCUpload")

    @abstractmethod
    def close(self, resource):
        """
        Custom implementation of the upload behaviour.
        Method shouldn't be called directly, but rather invoked via context (__exit__).
        close() should take a resource returned by corresponding open() and clean it up.
        """
        raise Exception("Operation is not supported: close() invoked on abstract base class - DVCUpload")


class DVCCallbackUpload(DVCUpload):
    """
    Upload string content generated by a callback function to the DVC
    """
    # Path to the local file
    data_provider: Callable[[], str]

    def __init__(self, dvc_path: str, data_provider: Callable[[], str]):
        super().__init__(dvc_path=dvc_path)
        self.data_provider = data_provider

    def describe_source(self) -> str:
        return f"Callback {self.instance_context}"

    def open(self):
        return StringIO(self.data_provider())

    def close(self, resource):
        # No need to close string io
        pass


class DVCPathUpload(DVCUpload):
    """
    Upload local file to DVC using its system path
    """
    # Path to the local file
    src: str

    def __init__(self, dvc_path: str, local_path: str):
        super().__init__(dvc_path=dvc_path)
        self.src = local_path

    def describe_source(self) -> str:
        return f"Path {self.src}"

    def open(self):
        # Open the file
        return open(self.src, 'r')

    def close(self, resource):
        # Close the file opened by open()
        resource.close()


class DVCS3Upload(DVCUpload):
    """
    Upload item from S3 to DVC
    This is useful when you have S3Hook in your workflows used
    as a temporary cache for files and you're not using shared-filesystem,
    so using DVCPathUpload is not an option.
    """
    # Connection ID (the same as for Airflow S3Hook)
    # For more details please see:
    # - https://airflow.apache.org/docs/apache-airflow/1.10.14/_modules/airflow/hooks/S3_hook.html
    # - https://www.programcreek.com/python/example/120741/airflow.hooks.S3_hook.S3Hook
    aws_conn_id: str
    # Bucket name (see above)
    bucket_name: str
    # Bucket path for the downloaded file (see above)
    bucket_path: str

    def __init__(self, dvc_path: str, aws_conn_id: str, bucket_name: str, bucket_path: str):
        super().__init__(dvc_path=dvc_path)
        self.aws_conn_id = aws_conn_id
        self.bucket_name = bucket_name
        self.bucket_path = bucket_path

    def describe_source(self) -> str:
        return f"S3 {self.bucket_name}/{self.bucket_path}"

    def open(self):
        # Open connection to the S3 and download the file
        s3_hook = S3Hook(aws_conn_id=self.aws_conn_id)
        return StringIO(
            s3_hook.read_key(key=self.bucket_path, bucket_name=self.bucket_name)
        )

    def close(self, resource):
        # Closing is not necessary for S3
        pass


class DVCStringUpload(DVCUpload):
    """
    Upload DVC object from a string.
    This is useful when the content of the file is determined at the moment when
    Airflow is building the DAG.
    If you don't want to create unnecessary files, DVCStringUpload allows you to upload
    string content as a DVC file.
    """
    # Content of the file
    content: str

    def __init__(self, dvc_path: str, content: str):
        super().__init__(dvc_path=dvc_path)
        self.content = content

    def describe_source(self) -> str:
        return f"String {self.instance_context}"

    def open(self):
        # Open string for reading
        return StringIO(self.content)

    def close(self, resource):
        # Closing is not required
        pass
