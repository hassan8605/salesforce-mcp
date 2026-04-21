from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class BuildJSONResponses:
    @staticmethod
    def success_response(data=None, message=None, status_code=status.HTTP_200_OK):
        return JSONResponse(
            content={
                "data": jsonable_encoder(data),
                "succeeded": True,
                "message": message,
                "httpStatusCode": status_code,
            },
            status_code=status.HTTP_200_OK,
        )

    @staticmethod
    def raise_exception(message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        return JSONResponse(
            content={"succeeded": False, "message": str(message)},
            status_code=status_code,
        )

    @staticmethod
    def server_error(message: str = "Internal server error."):
        return JSONResponse(
            content={"succeeded": False, "message": str(message)},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
