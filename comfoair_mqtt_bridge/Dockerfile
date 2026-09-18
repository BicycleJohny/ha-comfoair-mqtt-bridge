ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY run.sh /run.sh
COPY app.py protocol.py /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
