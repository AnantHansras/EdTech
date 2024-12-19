const Course = require("../models/Course");
const RatingAndReview = require('../models/RatingAndReview');

//createRating
exports.createRating = async (req,res) =>{
    try{
        //get user id
        const userId = req.user.id;

        //fetch data from req body
        const {rating,review,courseId} = req.body;

        //check if user is enrolled or not
        const courseDetails = await Course.findOne(
            {_id:courseId,
                studentsEnrolled:{$elemMatch : {$eq:userId}},
            }
        );
        if(!courseDetails){
            return res.status(404).json({
                success:false,
                message:'Students is not enrolled in the course'
            });
        }

        //check if user already reviewed the course
        const alreadyReviewed = await RatingAndReview.findOne({
            user:userId,
            course:courseId
        });
        if(alreadyReviewed){
            return res.status(404).json({
                success:false,
                message:'Students already reviewed this course'
            });
        }

        //create rating and review
        const ratingReview = await RatingAndReview.create({
            rating,
            review,
            course:courseId,
            user:userId
        });

        //update course with rating and review id
        await Course.findByIdAnsUpdate({_id:courseId},
            {
            $push:{
                RatingAndReviews:ratingReview._id
            }
        },
            {new:true}
        );

        
        return res.status(400).json({
            success:true,
            message:"Rating and review created successfully"
        });
        
    }
    catch(err){
        return res.status(400).json({
            success:false,
            message:err.message
        });
    }
}

//averageRating
exports.getAverageRating = async (req,res) =>{
    try{
        const {courseId} = req.body;

        const result = await RatingAndReview.aggregate({
                $match:{
                    course: new mongoose.Types.ObjectId(courseId),
                }
            },
            {
                $group:{
                    _id:null,
                    averageRating:{$avg: "$rating"}
                }
            }
        );

        if(result.length > 0){
            return res.status(400).json({
                success:true,
                averageRating:result[0].averageRating
            });
        }

        return res.status(400).json({
            success:true,
            message:"No reviews till now for this course",
            averageRating:0
        });
    }
    catch(err){
        return res.status(400).json({
            success:false,
            message:err.message
        });
    }
}

//getAllRatingAndReviews
exports.getAllRating = async (req,res) =>{
    try{
        const allReviews = RatingAndReview.find({})
        .sort({rating:"desc"})
        .populate({
            path:"user",
            select:"firstname lastName email image"
        })
        .populate({
            path:"course",
            select:"courseName"
        })
        .exec();
        return res.status(200).json({
            success:true,
            message:"Fetched all rating and reviews",
            data:allReviews
        });
    }
    catch(err){
        return res.status(400).json({
            success:false,
            message:err.message
        });
    }
}