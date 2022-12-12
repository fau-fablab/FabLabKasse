FROM ubuntu:18.04
ADD install_debian.sh /
ENV DOCKER=1
RUN mkdir /FabLabKasse_setup/
ADD requirements.txt /FabLabKasse_setup/
ADD install_debian.sh /FabLabKasse_setup/
WORKDIR /FabLabKasse_setup
RUN yes | ./install_debian.sh
CMD xeyes
