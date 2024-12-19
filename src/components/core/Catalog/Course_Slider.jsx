import React, { useEffect, useState } from "react"
// Import Swiper React components
import { Swiper, SwiperSlide } from "swiper/react"

// Import Swiper styles
import "swiper/css"
import "swiper/css/free-mode"
import "swiper/css/pagination"
// import "../../.."
// Import required modules
import {Autoplay, FreeMode, Pagination } from "swiper/modules"

// import { getAllCourses } from "../../services/operations/courseDetailsAPI"
import Course_Card from "./Course_Card"

function Course_Slider({ Courses }) {
  return (
    <>
      {Courses?.length ? (
        <Swiper
          slidesPerView={3}
          spaceBetween={25}
          loop={true}
          freeMode={true} // Enable FreeMode
          pagination={{ clickable: true }} // Enable Pagination
          autoplay={{
          delay: 3000, // Slide transition delay in milliseconds
          disableOnInteraction: false, // Continue autoplay after interaction
           }}
          modules={[FreeMode, Pagination,Autoplay]}
          breakpoints={{
            1024: {
              slidesPerView: 3,
            },
          }}
          className="max-h-[30rem]"
        >
          {Courses?.map((course, i) => (
            <SwiperSlide key={i}>
              <Course_Card course={course} Height={"h-[250px]"} />
            </SwiperSlide>
          ))}
        </Swiper>
      ) : (
        <p className="text-xl text-richblack-500">No Course Found</p>
      )}
    </>
  )
}

export default Course_Slider
